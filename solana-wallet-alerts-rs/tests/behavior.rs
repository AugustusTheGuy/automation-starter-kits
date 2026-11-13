use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use solana_wallet_alerts_rs::{
    activity_line, b58encode, gate, killed, load_seen, local_label, parse_args, partition_watches,
    program_accounts_query, should_send_telegram, targets_from_program_accounts, telegram_request,
    valid_pubkey, watch_entry_disc, Gate, DEFAULT_PROGRAM,
};

const SYSTEM: &str = "11111111111111111111111111111111";
const DISC: [u8; 8] = [126, 80, 144, 98, 34, 115, 191, 6];

#[test]
fn filters_memcmp_discriminator_and_registry() {
    let mut hasher = Sha256::new();
    hasher.update(b"account:WatchEntry");
    let digest = hasher.finalize();
    assert_eq!(&digest[..8], &DISC);

    let query = program_accounts_query(DEFAULT_PROGRAM, SYSTEM);
    assert_eq!(DEFAULT_PROGRAM, "Cy8SDxDGjFoxsiYvePXq67pdfiLgfJurcqUaTPD557a3");
    assert_eq!(query["method"], "getProgramAccounts");
    assert_eq!(query["params"][0], DEFAULT_PROGRAM);
    assert_eq!(query["params"][1]["encoding"], "base64");
    let filters = &query["params"][1]["filters"];
    assert_eq!(filters[0]["memcmp"]["offset"], 0);
    assert_eq!(filters[1]["memcmp"]["offset"], 8);
    assert_eq!(filters[1]["memcmp"]["bytes"], SYSTEM);
    assert_eq!(watch_entry_disc(), DISC);
    assert_eq!(filters[0]["memcmp"]["bytes"], b58encode(&DISC));
}

#[test]
fn reads_target_pubkey_from_account_bytes() {
    let data = [
        DISC.as_slice(),
        &[0u8; 32][..],
        &[0u8; 32][..],
        &0u64.to_le_bytes(),
        &[0u8; 32][..],
        &[1u8],
    ]
    .concat();
    let body = json!([{ "account": { "data": [STANDARD.encode(data), "base64"] } }]);
    assert_eq!(targets_from_program_accounts(&body), vec![SYSTEM.to_string()]);
}

#[test]
fn registry_flag_parses_without_a_keypair() {
    let with = parse_args(&[String::from("--registry"), String::from(SYSTEM)]);
    assert_eq!(with.registry, SYSTEM);
    assert_eq!(parse_args(&[]).registry, "");
}

#[test]
fn pubkey_rules_match_the_python_bot() {
    assert!(valid_pubkey(SYSTEM));
    assert!(valid_pubkey("Fe2dGytY15xzbqL23RBTT9wCG85CHGtyHCuysiL93uXe"));
    assert!(valid_pubkey("Cy8SDxDGjFoxsiYvePXq67pdfiLgfJurcqUaTPD557a3"));
    assert!(!valid_pubkey("not-a-key"));
    assert!(!valid_pubkey(&"0OIl".repeat(10)));
    let (good, bad) = partition_watches(&[SYSTEM, "nope"]);
    assert_eq!(good, vec![SYSTEM.to_string()]);
    assert_eq!(bad, vec![String::from("nope")]);
}

fn sample_tx(addr: &str, pre: u64, post: u64, mints: &[&str]) -> Value {
    let tokens: Vec<_> = mints
        .iter()
        .map(|mint| json!({"mint": mint, "owner": addr}))
        .collect();
    json!({
        "meta": {
            "preBalances": [pre],
            "postBalances": [post],
            "preTokenBalances": [],
            "postTokenBalances": tokens
        },
        "transaction": { "message": { "accountKeys": [{ "pubkey": addr }] } }
    })
}

#[test]
fn gate_passes_when_no_floor_and_no_allowlist() {
    assert_eq!(gate(0.0, &[], "addr", &Value::Null), Gate::Alert);
}

#[test]
fn gate_skips_a_move_under_min_sol() {
    let tx = sample_tx("addr", 2_000_000_000, 2_100_000_000, &[]);
    assert_eq!(gate(1.0, &[], "addr", &tx), Gate::Skip);
}

#[test]
fn gate_alerts_when_the_move_meets_min_sol() {
    let tx = sample_tx("addr", 1_000_000_000, 3_000_000_000, &[]);
    assert_eq!(gate(1.0, &[], "addr", &tx), Gate::Alert);
}

#[test]
fn gate_retries_when_the_transaction_is_missing() {
    assert_eq!(gate(1.0, &[], "addr", &Value::Null), Gate::Retry);
}

#[test]
fn gate_skips_when_the_allowlist_mint_is_absent() {
    let tx = sample_tx("addr", 0, 0, &[]);
    assert_eq!(gate(0.0, &[String::from(SYSTEM)], "addr", &tx), Gate::Skip);
}

#[test]
fn gate_alerts_when_the_allowlist_mint_is_present() {
    let tx = sample_tx("addr", 0, 0, &[SYSTEM]);
    assert_eq!(gate(0.0, &[String::from(SYSTEM)], "addr", &tx), Gate::Alert);
}

#[test]
fn gate_reads_string_account_keys() {
    let tx = json!({
        "meta": {
            "preBalances": [0],
            "postBalances": [2_000_000_000],
            "preTokenBalances": [],
            "postTokenBalances": []
        },
        "transaction": { "message": { "accountKeys": ["addr"] } }
    });
    assert_eq!(gate(1.0, &[], "addr", &tx), Gate::Alert);
}

#[test]
fn seen_store_expires_after_seven_days_and_accepts_a_list() {
    let now = 1_700_000_000.0;
    let raw = json!({"old": now - 8.0 * 86_400.0, "new": now - 10.0}).to_string();
    let seen = load_seen(&raw, now);
    assert!(seen.contains_key("new"));
    assert!(!seen.contains_key("old"));
    let listed = load_seen(&json!(["sig"]).to_string(), 100.0);
    assert_eq!(listed.get("sig"), Some(&100.0));
}

#[test]
fn kill_file_or_switch_stops_the_poller() {
    let path = std::env::temp_dir().join(format!("watch-alerts-kill-{}", std::process::id()));
    let _ = std::fs::remove_file(&path);
    assert!(!killed(&path, "0"));
    std::fs::write(&path, b"").unwrap();
    assert!(killed(&path, "0"));
    std::fs::remove_file(&path).unwrap();
    assert!(killed(&path, "1"));
    assert!(!killed(&path, "0"));
}

#[test]
fn dry_run_labels_the_local_line() {
    assert_eq!(local_label(true), "[DRY]");
    assert_eq!(local_label(false), "[LOCAL]");
    assert!(!should_send_telegram("tok", "chat", true));
    assert!(!should_send_telegram("", "chat", false));
    assert!(should_send_telegram("tok", "chat", false));
    let (url, body) = telegram_request("tok", "chat", "hi");
    assert_eq!(url, "https://api.telegram.org/bottok/sendMessage");
    assert_eq!(body["chat_id"], "chat");
    assert_eq!(body["text"], "hi");
}

#[test]
fn activity_line_matches_the_python_text() {
    let line = activity_line(SYSTEM, "abcdefghijklmnop", 9, false, 0.0);
    let short = format!("{}…{}", &SYSTEM[..6], &SYSTEM[SYSTEM.len() - 4..]);
    assert_eq!(line, format!("Activity on {short} sig=abcdefgh… slot=9"));
    let kept = activity_line("addraddraddr", "abcdefgh", 1, true, 1.5);
    assert_eq!(
        kept,
        "Activity on addraddraddr sig=abcdefgh… slot=1 allowlist=pass min_sol=1.5"
    );
    let whole = activity_line("abc", "abcdefgh", 1, false, 1.0);
    assert!(whole.ends_with("min_sol=1"));
}
