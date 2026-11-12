use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use solana_wallet_alerts_rs::{
    activity_line, gate, killed, load_seen, local_label, parse_args, partition_watches,
    program_accounts_query, should_send_telegram, targets_from_program_accounts, telegram_request,
    valid_pubkey, Gate, DEFAULT_PROGRAM,
};

#[tokio::main]
async fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.iter().any(|arg| arg == "--help" || arg == "-h") {
        println!("Read-only Solana watch alerts");
        println!("Usage: solana-wallet-alerts-rs [--registry PUBKEY]");
        return;
    }
    let parsed = parse_args(&args);
    let rpc_url = env::var("SOLANA_RPC").unwrap_or_else(|_| "https://api.mainnet-beta.solana.com".to_string());
    let dry = env::var("DRY_RUN").unwrap_or_else(|_| "1".to_string()) == "1";
    let min_sol: f64 = env::var("MIN_SOL").ok().and_then(|v| v.parse().ok()).unwrap_or(0.0);
    let poll_s: f64 = env::var("POLL_S").ok().and_then(|v| v.parse().ok()).unwrap_or(15.0);
    let program = env::var("WATCH_REGISTRY_PROGRAM").unwrap_or_else(|_| DEFAULT_PROGRAM.to_string());
    let token = env::var("TELEGRAM_BOT_TOKEN").unwrap_or_default();
    let chat = env::var("TELEGRAM_CHAT_ID").unwrap_or_default();
    let switch = env::var("KILL_SWITCH").unwrap_or_else(|_| "0".to_string());
    let allow: Vec<String> = env::var("MINT_ALLOWLIST")
        .unwrap_or_default()
        .split(',')
        .map(str::trim)
        .filter(|mint| valid_pubkey(mint))
        .map(str::to_string)
        .collect();
    let watch: Vec<String> = env::var("WATCH_ADDRESSES")
        .unwrap_or_default()
        .split(',')
        .map(str::trim)
        .filter(|addr| !addr.is_empty())
        .map(str::to_string)
        .collect();
    let seen_path = PathBuf::from("seen.json");
    let kill_path = PathBuf::from("KILL");
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(20))
        .build()
        .expect("http client");
    let mut seen = fs::read_to_string(&seen_path)
        .ok()
        .map(|raw| load_seen(&raw, now_secs()))
        .unwrap_or_default();

    if killed(&kill_path, &switch) {
        eprintln!("kill switch already set — exiting");
        return;
    }

    let good = if !parsed.registry.is_empty() {
        match rpc(&client, &rpc_url, &program_accounts_query(&program, &parsed.registry)).await {
            Ok(body) => targets_from_program_accounts(&body["result"])
                .into_iter()
                .filter(|addr| valid_pubkey(addr))
                .collect(),
            Err(err) => {
                eprintln!("registry read failed: {err}");
                return;
            }
        }
    } else {
        let refs: Vec<&str> = watch.iter().map(String::as_str).collect();
        let (good, bad) = partition_watches(&refs);
        for addr in bad {
            eprintln!("skip invalid address len={}", addr.len());
        }
        good
    };
    if good.is_empty() {
        eprintln!("Set WATCH_ADDRESSES or pass --registry");
        return;
    }
    eprintln!("watching {} dry={dry} (seen expires 7d)", good.len());

    loop {
        if killed(&kill_path, &switch) {
            eprintln!("kill switch triggered — clean exit");
            return;
        }
        for addr in &good {
            if killed(&kill_path, &switch) {
                break;
            }
            let query = json!({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [addr, {"limit": 5}]
            });
            let body = match rpc(&client, &rpc_url, &query).await {
                Ok(body) => body,
                Err(err) => {
                    eprintln!("poll {addr}: {err}");
                    continue;
                }
            };
            let mut changed = false;
            let now = now_secs();
            for item in body["result"].as_array().cloned().unwrap_or_default() {
                let Some(sig) = item["signature"].as_str() else { continue };
                let key = format!("{addr}|{sig}");
                if seen.contains_key(&key) {
                    continue;
                }
                let tx = if min_sol > 0.0 || !allow.is_empty() {
                    let q = json!({
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "getTransaction",
                        "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
                    });
                    match rpc(&client, &rpc_url, &q).await {
                        Ok(body) => body["result"].clone(),
                        Err(err) => {
                            eprintln!("gate {}: {err}", &sig[..sig.len().min(8)]);
                            Value::Null
                        }
                    }
                } else {
                    Value::Null
                };
                let decision = if min_sol <= 0.0 && allow.is_empty() {
                    Gate::Alert
                } else {
                    gate(min_sol, &allow, addr, &tx)
                };
                match decision {
                    Gate::Retry => continue,
                    Gate::Skip => {
                        seen.insert(key, now);
                        changed = true;
                        eprintln!("skip {} filter", &sig[..sig.len().min(8)]);
                    }
                    Gate::Alert => {
                        let slot = item["slot"].as_u64().unwrap_or(0);
                        let msg = activity_line(addr, sig, slot, !allow.is_empty(), min_sol);
                        let delivered = if should_send_telegram(&token, &chat, dry) {
                            let (url, payload) = telegram_request(&token, &chat, &msg);
                            match client.post(url).json(&payload).send().await {
                                Ok(response) if response.status().is_success() => true,
                                Ok(response) => {
                                    eprintln!("telegram: status {}", response.status());
                                    false
                                }
                                Err(err) => {
                                    eprintln!("telegram: {err}");
                                    false
                                }
                            }
                        } else {
                            println!("{} {msg}", local_label(dry));
                            true
                        };
                        if delivered {
                            seen.insert(key, now);
                            changed = true;
                        }
                    }
                }
            }
            if changed {
                save_seen(&seen_path, &seen, now);
            }
        }
        tokio::time::sleep(std::time::Duration::from_secs_f64(poll_s)).await;
    }
}

async fn rpc(client: &reqwest::Client, url: &str, body: &Value) -> Result<Value, String> {
    let response = client
        .post(url)
        .json(body)
        .send()
        .await
        .map_err(|err| err.to_string())?;
    let data: Value = response.json().await.map_err(|err| err.to_string())?;
    if let Some(err) = data.get("error") {
        if !err.is_null() {
            return Err(err.to_string());
        }
    }
    Ok(data)
}

fn now_secs() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

fn save_seen(path: &PathBuf, seen: &BTreeMap<String, f64>, now: f64) {
    let fresh: BTreeMap<_, _> = seen
        .iter()
        .filter(|(_, stamp)| now - **stamp < 7.0 * 24.0 * 3600.0)
        .map(|(k, v)| (k.clone(), *v))
        .collect();
    if let Ok(text) = serde_json::to_string(&fresh) {
        let _ = fs::write(path, text);
    }
}
