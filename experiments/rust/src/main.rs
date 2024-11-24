//use std::collections::HashMap;
use serde::{Deserialize};

#[derive(Debug, Deserialize)]
struct BuildResult {
    id: u64,
    jobset: String,
    nixname: String,
    system: String,
    buildstatus: u16,
    jobsetevals: Vec<u64>,
    timestamp: u64,
    job: String,
    project: String,
    finished: u16,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = reqwest::Client::new();
    let resp = client
        .get("https://hydra.nixos.org/build/202199463")
        .header("Content-Type", "application/json")
        .send()
        .await?
        .json::<BuildResult>()
        .await?;
    //println!("{}", resp.jobset);
    println!("{:#?}", resp);
    Ok(())
}

