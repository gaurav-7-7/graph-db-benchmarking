# Graph Database Benchmark: CognoDB vs. Neo4j vs. Memgraph vs. FalkorDB vs. ArangoDB

A rigorous, reproducible benchmark comparing five graph databases on identical hardware tiers,
the same dataset, and semantically equivalent queries.

> **Dataset**: SNAP soc-Pokec social network (sampled) · ~250K nodes · ~500K relationships  
> **Author**: [Your Name]  
> **Published article**: [Link to Dev.to / Medium post]

---

## TL;DR Results

<!-- Results table will be filled in after running benchmarks -->

| Benchmark | CognoDB | Neo4j AuraDB | Memgraph | FalkorDB | ArangoDB |
|-----------|---------|--------------|----------|----------|----------|
| Ingest throughput (nodes/s) | — | — | — | — | — |
| Ingest throughput (rels/s) | — | — | — | — | — |
| 1-hop p50 (ms) | — | — | — | — | — |
| 2-hop p50 (ms) | — | — | — | — | — |
| 3-hop p50 (ms) | — | — | — | — | — |
| Point lookup p50 (ms) | — | — | — | — | — |
| Filtered lookup p50 (ms) | — | — | — | — | — |
| Aggregation p50 (ms) | — | — | — | — | — |
| Mixed workload @ 10 clients (QPS) | — | — | — | — | — |

---

## Table of Contents

1. [Methodology](#methodology)
2. [Instance Specs](#instance-specs)
3. [Dataset](#dataset)
4. [How to Reproduce](#how-to-reproduce)
5. [Results](#results)
   - [Data Loading](#data-loading)
   - [Traversals](#traversals)
   - [Lookups](#lookups)
   - [Aggregations](#aggregations)
   - [Mixed Workload](#mixed-workload)
   - [Resource Footprint](#resource-footprint)
6. [Analysis](#analysis)
7. [Caveats](#caveats)

---

## Methodology

### Fairness Principles

- **Same resources**: All databases run on equivalent or smaller free/entry tiers. Specs documented below.
- **Same dataset**: Identical CSV files loaded into every platform.
- **Same queries**: Semantically equivalent queries (Cypher for CognoDB/AuraDB/Memgraph/FalkorDB, AQL for ArangoDB). Query translations are documented in `benchmarks/`.
- **Same client machine**: All benchmarks run from [your machine/region].
- **Warm-up**: 10 warm-up iterations before measurement begins. Cold-start numbers are excluded from p50/p95.
- **Iterations**: ≥100 measurement iterations per query per database.
- **Percentiles**: We report p50 and p95, not just averages. Raw latency arrays are saved to `results/raw/`.

### Query Definitions

| Benchmark | Cypher | AQL (ArangoDB) |
|-----------|--------|----------------|
| 1-hop traversal | `MATCH (n:User {user_id: $id})-[:FOLLOWS]->(m) RETURN count(m)` | `FOR v IN 1..1 OUTBOUND 'benchmark_users/$id' GRAPH 'benchmark_graph' COLLECT WITH COUNT INTO cnt RETURN cnt` |
| 2-hop traversal | `MATCH (n:User {user_id: $id})-[:FOLLOWS*2]->(m) RETURN count(m)` | `FOR v IN 2..2 OUTBOUND ...` |
| 3-hop traversal | `MATCH (n:User {user_id: $id})-[:FOLLOWS*3]->(m) RETURN count(m)` | `FOR v IN 3..3 OUTBOUND ...` |
| Point lookup | `MATCH (n:User {user_id: $id}) RETURN n` | `FOR u IN benchmark_users FILTER u.user_id == @id RETURN u` |
| Filtered lookup | `MATCH (n:User) WHERE n.age > 25 AND n.gender = '1' RETURN count(n)` | `FOR u IN benchmark_users FILTER u.age > 25 AND u.gender == '1' COLLECT WITH COUNT INTO cnt RETURN cnt` |
| Aggregation | `MATCH (n)-[:FOLLOWS]->(m) RETURN m.gender, count(*) ORDER BY count(*) DESC LIMIT 10` | `FOR e IN benchmark_follows FOR v IN benchmark_users FILTER v._id == e._to COLLECT gender = v.gender WITH COUNT INTO cnt SORT cnt DESC LIMIT 10 RETURN {gender, cnt}` |

---

## Instance Specs

| Database | Tier | vCPU | RAM | Disk | Region |
|----------|------|------|-----|------|--------|
| CognoDB Cloud | Free (c0) | 0.5 (burstable) | 256 MB | 1 GB | [your region] |
| Neo4j AuraDB | Free | 1 | 1 GB | 2 GB | [your region] |
| Memgraph Cloud | Free | ~0.5 | 256 MB | — | [your region] |
| FalkorDB | Docker (`--cpus=0.5 --memory=256m`) | 0.5 | 256 MB | unlimited | local |
| ArangoDB | Docker (`--cpus=0.5 --memory=256m`) | 0.5 | 256 MB | unlimited | local |

> **Note**: Neo4j AuraDB free tier provides more RAM (1 GB) than CognoDB (256 MB). This resource
> difference is documented as a caveat; where it materially affects results, it is noted in the
> analysis. Benchmarking on unequal tiers is a methodology error — we document this honestly rather
> than obscure it.

---

## Dataset

**Source**: [SNAP soc-Pokec](https://snap.stanford.edu/data/soc-pokec.html) — Slovak social network  
**Full dataset**: 1,632,803 nodes, 30,622,564 directed edges  
**Sampled subset used**: ~250,000 nodes, ~500,000 edges (induced subgraph, seed=42)

**Node properties**: `user_id`, `gender`, `age`, `region`  
**Edge type**: `FOLLOWS` (directed)

**Indexes created on all platforms**:
- `user_id` (primary / unique)
- `age` (for filtered lookup)
- `gender` (for filtered lookup)

**Load method per platform**:

| Database | Load method |
|----------|-------------|
| CognoDB | `neo4j` Python driver — `UNWIND $batch MERGE (u:User)`, batch size 500 |
| Neo4j AuraDB | Same as above |
| Memgraph | Same as above |
| FalkorDB | Same as above |
| ArangoDB | `python-arango` `import_bulk()`, batch size 500 |

---

## How to Reproduce

### Prerequisites

- Python 3.10+
- Docker + Docker Compose (for FalkorDB + ArangoDB)
- Free accounts on: [CognoDB Cloud](https://console.cognodb.com/signup), [Neo4j AuraDB](https://neo4j.com/cloud/platform/aura-graph-database/), [Memgraph Cloud](https://memgraph.com/cloud)

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/graph-db-benchmarking
cd graph-db-benchmarking
```

### 2. Install Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Start local databases

```bash
docker compose up -d
# Wait ~30s for ArangoDB to initialize
```

### 4. Configure credentials

```bash
cp .env.example .env
# Edit .env with your cloud DB credentials
```

### 5. Download and sample the dataset

```bash
bash data/download.sh      # ~1.2 GB download
python data/sample.py      # Creates data/nodes.csv + data/edges.csv
```

### 6. Run the full benchmark

```bash
# Load data into all 5 databases
python orchestrator/run_all.py --phase load --db all

# Run all benchmarks (takes ~30–60 min total)
python orchestrator/run_all.py --phase bench --db all
```

Or run a single database:

```bash
python orchestrator/run_all.py --phase all --db cognodb
```

### 7. Generate charts and summary tables

```bash
python analysis/generate_report.py \
  --seq  results/raw/sequential_results_YYYYMMDD_HHMMSS.csv \
  --mixed results/raw/mixed_workload_YYYYMMDD_HHMMSS.csv \
  --out  results/charts
```

---

## Results

### Data Loading

<!-- Fill after running -->

| Database | Nodes/sec | Rels/sec | Total load time |
|----------|-----------|----------|-----------------|
| CognoDB | — | — | — |
| Neo4j AuraDB | — | — | — |
| Memgraph | — | — | — |
| FalkorDB | — | — | — |
| ArangoDB | — | — | — |

### Traversals

<!-- Fill after running -->

**p50 Latency (ms)**

| Benchmark | CognoDB | Neo4j AuraDB | Memgraph | FalkorDB | ArangoDB |
|-----------|---------|--------------|----------|----------|----------|
| 1-hop | — | — | — | — | — |
| 2-hop | — | — | — | — | — |
| 3-hop | — | — | — | — | — |

**p95 Latency (ms)**

| Benchmark | CognoDB | Neo4j AuraDB | Memgraph | FalkorDB | ArangoDB |
|-----------|---------|--------------|----------|----------|----------|
| 1-hop | — | — | — | — | — |
| 2-hop | — | — | — | — | — |
| 3-hop | — | — | — | — | — |

![Traversal Latency Chart](results/charts/traversal_latency.png)

### Lookups

<!-- Fill after running -->

| Benchmark | CognoDB p50 | CognoDB p95 | AuraDB p50 | AuraDB p95 | Memgraph p50 | Memgraph p95 | FalkorDB p50 | FalkorDB p95 | ArangoDB p50 | ArangoDB p95 |
|-----------|-------------|-------------|------------|------------|--------------|--------------|--------------|--------------|--------------|--------------|
| Point lookup | — | — | — | — | — | — | — | — | — | — |
| Filtered lookup | — | — | — | — | — | — | — | — | — | — |

### Aggregations

<!-- Fill after running -->

| Database | p50 (ms) | p95 (ms) |
|----------|----------|----------|
| CognoDB | — | — |
| Neo4j AuraDB | — | — |
| Memgraph | — | — |
| FalkorDB | — | — |
| ArangoDB | — | — |

![Lookup + Aggregation Chart](results/charts/lookup_aggregation.png)

### Mixed Workload

70% reads (2-hop traversal) / 30% writes (CREATE + DELETE relationship)  
Duration: 30 seconds per concurrency level

**Queries per second**

| Clients | CognoDB | Neo4j AuraDB | Memgraph | FalkorDB | ArangoDB |
|---------|---------|--------------|----------|----------|----------|
| 1 | — | — | — | — | — |
| 10 | — | — | — | — | — |
| 40 | — | — | — | — | — |

![Mixed Workload QPS](results/charts/mixed_workload_qps.png)

### Resource Footprint

| Database | Data size on disk | Memory usage | Notes |
|----------|-------------------|--------------|-------|
| CognoDB | — | not observable | Cloud-managed |
| Neo4j AuraDB | — | not observable | Cloud-managed |
| Memgraph | — | not observable | Cloud-managed |
| FalkorDB | — | from `docker stats` | |
| ArangoDB | — | from `docker stats` | |

---

## Analysis

> _[To be filled after benchmarks run. ~400 words covering: which DB was fastest for which workload, why FalkorDB's Redis-based storage affects latency, why in-memory Memgraph behaves differently under concurrency vs. disk-backed DBs, CognoDB's position relative to the baseline Neo4j AuraDB, and AQL vs. Cypher query plan differences.]_

---

## Caveats

- **Resource parity**: Neo4j AuraDB free tier provides 1 GB RAM vs. 256 MB for CognoDB/Memgraph/FalkorDB/ArangoDB. Where this materially affects results, it is noted in the analysis. This is a free-tier limitation, not a methodology choice.
- **Network latency**: Cloud DBs (CognoDB, AuraDB, Memgraph) include round-trip network latency to their cloud endpoint. FalkorDB and ArangoDB are local (sub-ms network). This is inherent to managed vs. self-hosted comparison and is documented, not obscured.
- **Free-tier throttling**: Some platforms may throttle burst connections. Any observed throttling, timeout, or rate-limit is logged in `results/raw/` and noted in the analysis.
- **Cypher vs. AQL**: ArangoDB uses AQL, not Cypher. Queries are semantically equivalent but execution plans differ. The AQL query for each benchmark is documented in the Methodology section.
- **Cold-start**: All numbers are warm (10 warm-up iterations discarded). Cold-start results were not measured separately.
- **Single client machine**: All benchmarks were run from one machine (`[OS, CPU, RAM, region]`). Network path to cloud endpoints may differ from your environment.

---

## License

MIT

---

## Acknowledgements

Dataset: Backstrom, L., Huttenlocher, D., Kleinberg, J., Lan, X. (2006). Group formation in large social networks. *KDD '06*. Stanford SNAP.
