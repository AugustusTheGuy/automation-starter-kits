use std::collections::BTreeMap;
use std::path::Path;

use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

pub const DEFAULT_PROGRAM: &str = "Cy8SDxDGjFoxsiYvePXq67pdfiLgfJurcqUaTPD557a3";
const B58: &[u8] = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
const EXPIRE_S: f64 = 7.0 * 24.0 * 3600.0;

#[derive(Debug, PartialEq, Eq)]
pub enum Gate {
    Alert,
    Skip,
    Retry,
}

pub struct Args {
    pub registry: String,
}

pub fn watch_entry_disc() -> [u8; 8] {
    let digest = Sha256::digest(b"account:WatchEntry");
    let mut out = [0u8; 8];
    out.copy_from_slice(&digest[..8]);
    out
}

pub fn b58encode(raw: &[u8]) -> String {
    let zeros = raw.iter().take_while(|byte| **byte == 0).count();
    if raw.iter().all(|byte| *byte == 0) {
        return "1".repeat(raw.len());
    }
    let mut num = raw.to_vec();
    let mut chars = Vec::new();
    while num.iter().any(|byte| *byte != 0) {
        let mut rem = 0u32;
        for byte in &mut num {
            let acc = rem * 256 + u32::from(*byte);
            *byte = (acc / 58) as u8;
            rem = acc % 58;
        }
        chars.push(B58[rem as usize] as char);
    }
    let mut out = "1".repeat(zeros);
    for ch in chars.into_iter().rev() {
        out.push(ch);
    }
    out
}

pub fn valid_pubkey(addr: &str) -> bool {
    let bytes = addr.as_bytes();
    if !(32..=44).contains(&bytes.len()) {
        return false;
    }
    let mut acc = vec![0u8];
    for &ch in bytes {
        let Some(index) = B58.iter().position(|c| *c == ch) else {
            return false;
        };
        let mut carry = index as u32;
        for byte in acc.iter_mut().rev() {
            let value = u32::from(*byte) * 58 + carry;
            *byte = (value & 0xff) as u8;
            carry >>= 8;
        }
        while carry > 0 {
            acc.insert(0, (carry & 0xff) as u8);
            carry >>= 8;
        }
    }
    let pad = bytes.iter().take_while(|ch| **ch == b'1').count();
    let mut body = acc.as_slice();
    while body.first() == Some(&0) {
        body = &body[1..];
    }
    pad + body.len() == 32
}

pub fn program_accounts_query(program_id: &str, registry: &str) -> Value {
    json!({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getProgramAccounts",
        "params": [
            program_id,
            {
                "encoding": "base64",
                "filters": [
                    {"memcmp": {"offset": 0, "bytes": b58encode(&watch_entry_disc())}},
                    {"memcmp": {"offset": 8, "bytes": registry}}
                ]
            }
        ]
    })
}

pub fn targets_from_program_accounts(result: &Value) -> Vec<String> {
    let disc = watch_entry_disc();
    let Some(rows) = result.as_array() else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for row in rows {
        let raw = &row["account"]["data"];
        let blob = if let Some(parts) = raw.as_array() {
            parts.first().and_then(Value::as_str).unwrap_or("")
        } else {
            raw.as_str().unwrap_or("")
        };
        if blob.is_empty() {
            continue;
        }
        let Ok(data) = STANDARD.decode(blob) else {
            continue;
        };
        if data.len() < 72 || data[..8] != disc {
            continue;
        }
        out.push(b58encode(&data[40..72]));
    }
    out
}

pub fn parse_args(argv: &[String]) -> Args {
    let mut registry = String::new();
    let mut index = 0;
    while index < argv.len() {
        if argv[index] == "--registry" {
            if let Some(value) = argv.get(index + 1) {
                registry = value.clone();
                index += 2;
                continue;
            }
        }
        index += 1;
    }
    Args { registry }
}

pub fn partition_watches(addrs: &[&str]) -> (Vec<String>, Vec<String>) {
    let mut good = Vec::new();
    let mut bad = Vec::new();
    for addr in addrs {
        if valid_pubkey(addr) {
            good.push((*addr).to_string());
        } else {
            bad.push((*addr).to_string());
        }
    }
    (good, bad)
}

pub fn gate(min_sol: f64, allow: &[String], addr: &str, tx: &Value) -> Gate {
    if min_sol <= 0.0 && allow.is_empty() {
        return Gate::Alert;
    }
    if tx.is_null() {
        return Gate::Retry;
    }
    let meta = &tx["meta"];
    if min_sol > 0.0 {
        let owners: Vec<String> = tx["transaction"]["message"]["accountKeys"]
            .as_array()
            .map(|keys| {
                keys.iter()
                    .map(|key| {
                        key.as_str()
                            .unwrap_or_else(|| key["pubkey"].as_str().unwrap_or(""))
                            .to_string()
                    })
                    .collect()
            })
            .unwrap_or_default();
        let Some(index) = owners.iter().position(|owner| owner == addr) else {
            return Gate::Skip;
        };
        let Some(pre) = meta["preBalances"].as_array() else {
            return Gate::Skip;
        };
        let Some(post) = meta["postBalances"].as_array() else {
            return Gate::Skip;
        };
        if index >= pre.len() || index >= post.len() {
            return Gate::Skip;
        }
        let pre_n = json_u64(&pre[index]);
        let post_n = json_u64(&post[index]);
        let diff = (pre_n as i128 - post_n as i128).unsigned_abs() as f64 / 1_000_000_000.0;
        if diff < min_sol {
            return Gate::Skip;
        }
    }
    if !allow.is_empty() {
        let blob = format!("{}{}", meta["preTokenBalances"], meta["postTokenBalances"]);
        if !allow.iter().any(|mint| blob.contains(mint.as_str())) {
            return Gate::Skip;
        }
    }
    Gate::Alert
}

fn json_u64(value: &Value) -> u64 {
    value.as_u64().unwrap_or_else(|| value.as_i64().unwrap_or(0) as u64)
}

pub fn load_seen(raw: &str, now: f64) -> BTreeMap<String, f64> {
    let mut seen = BTreeMap::new();
    let Ok(value) = serde_json::from_str::<Value>(raw) else {
        return seen;
    };
    if let Some(list) = value.as_array() {
        for item in list {
            if let Some(sig) = item.as_str() {
                seen.insert(sig.to_string(), now);
            }
        }
        return seen;
    }
    if let Some(obj) = value.as_object() {
        for (key, stamp) in obj {
            let Some(stamp) = stamp.as_f64().or_else(|| stamp.as_i64().map(|n| n as f64)) else {
                continue;
            };
            if now - stamp < EXPIRE_S {
                seen.insert(key.clone(), stamp);
            }
        }
    }
    seen
}

pub fn killed(kill_file: &Path, switch: &str) -> bool {
    kill_file.exists() || switch == "1"
}

pub fn local_label(dry: bool) -> &'static str {
    if dry {
        "[DRY]"
    } else {
        "[LOCAL]"
    }
}

pub fn should_send_telegram(token: &str, chat: &str, dry: bool) -> bool {
    !dry && !token.is_empty() && !chat.is_empty()
}

pub fn telegram_request(token: &str, chat: &str, text: &str) -> (String, Value) {
    (
        format!("https://api.telegram.org/bot{token}/sendMessage"),
        json!({"chat_id": chat, "text": text}),
    )
}

pub fn activity_line(addr: &str, sig: &str, slot: u64, allow: bool, min_sol: f64) -> String {
    let short = short_addr(addr);
    let sig8: String = sig.chars().take(8).collect();
    let mut msg = format!("Activity on {short} sig={sig8}… slot={slot}");
    if allow {
        msg.push_str(" allowlist=pass");
    }
    if min_sol > 0.0 {
        msg.push_str(&format!(" min_sol={}", format_sol(min_sol)));
    }
    msg
}

fn short_addr(addr: &str) -> String {
    let chars: Vec<char> = addr.chars().collect();
    if chars.len() <= 12 {
        return addr.to_string();
    }
    let head: String = chars[..6].iter().collect();
    let tail: String = chars[chars.len() - 4..].iter().collect();
    format!("{head}…{tail}")
}

fn format_sol(value: f64) -> String {
    let text = format!("{value:.6}");
    let trimmed = text.trim_end_matches('0').trim_end_matches('.');
    if trimmed.is_empty() {
        "0".to_string()
    } else {
        trimmed.to_string()
    }
}
