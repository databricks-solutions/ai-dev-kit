# Blog-to-Skill Conversion Manifest

## Summary

This manifest documents the conversion of technical blog posts from `databricksters.com` and `canadiandataguy.com` into Databricks Agent Skills.

**Conversion Date**: 2026-02-04  
**Total Skills Created**: 6  
**Total Blog Posts Processed**: 53  
**Conversion Rate**: ~11% (actionable technical content only)

---

## databricksters.com Skills

| Skill Name | Blog Title | Author | Conversion Date | Status |
|------------|------------|--------|-----------------|--------|
| databricks-vacuum | Your Storage Bill Is Too High. Here Are 3 Levels of VACUUM to Fix It | Canadian Data Guy | 2026-02-04 | ✅ Complete |
| databricks-sql-warehouse-tuning | 10 Lessons from Analyzing and Tuning Two Dozen Databricks SQL Warehouses | Artem Chebotko | 2026-02-04 | ✅ Complete |
| aibi-dashboard-filters | Migrating Existing Dashboards to Databricks AI/BI, Part 1: Context and Cascading Filters | Artem Chebotko | 2026-02-04 | ✅ Complete |
| salesforce-batch-writer | Bulking Up: High-Performance Batch Salesforce Writes with PySpark | Neil Wilson | 2026-02-04 | ✅ Complete |

## canadiandataguy.com Skills

| Skill Name | Blog Title | Author | Conversion Date | Status |
|------------|------------|--------|-----------------|--------|
| liquid-clustering-guide | How to Choose Between Liquid Clustering and Partitioning with Z-Order in Databricks | Canadian Data Guy, Geethu | 2026-02-04 | ✅ Complete |
| delta-streaming-exactly-once | Inside Delta Lake's Idempotency Magic: The Secret to Exactly-Once Spark | Canadian Data Guy | 2026-02-04 | ✅ Complete |

---

## Skipped Blogs

The following blogs were identified but not converted to skills:

### databricksters.com (Skipped - 37 posts)

| Blog Title | Reason for Skipping |
|------------|---------------------|
| Liquid Clustering at Scale: Overcoming Challenges and Unlocking Performance | Covered by liquid-clustering-guide skill |
| Building Useful AI Agents with Agent Bricks | Conceptual overview, duplicates agent-bricks skill |
| Databricks Zerobus Ingest — The Best Bus Is No Bus | Conceptual architecture |
| Cheese and Rice, that's config.json Bourne | Specific use case (fine-tuning endpoints) |
| Trace your steps back to Slack | Specific integration (Slack bot) |
| Your Low-Code Shortcut to Production-Grade Agent on Databricks | Video content, duplicates agent-bricks skill |
| The Goldilocks Approach: Hierarchical Classification with AI_QUERY | Narrow use case |
| Warming Up Databricks SQL Disk Cache for Reliable BI Dashboard Benchmarking | Very specific benchmarking scenario |
| Integrate Teams with Genie using webhooks | Specific integration, duplicates databricks-genie skill |
| Integrate Slack with Genie natively | Specific integration, duplicates databricks-genie skill |
| Getting Medieval on Token Costs | Cost optimization discussion, less actionable |
| How Liquid DV and RLC help improve performance | Covered by liquid-clustering-guide |
| Agents are like onions, they have layers | Conceptual GenAI discussion |
| Doctors hate this one dependency | Specific troubleshooting scenario |
| Bayes'd and Redpilled | Statistical concept discussion |
| Beyond the Pipeline: The Blueprint for Bulletproof Data Workflows | Conceptual architecture |
| Securing GenAI Agents on Databricks | Security overview, duplicates existing skills |
| Understanding Embedding Model Pricing | Pricing analysis, not actionable |
| It's beaver time - Don't get logged down | Specific troubleshooting |
| Write Anywhere, Read Everywhere | Multi-region architecture, conceptual |
| Mastering Stream-Static Joins in Apache Spark | Advanced topic, covered by spark-declarative-pipelines |
| Chat with your data in Slack using Genie | Specific integration, duplicates databricks-genie |
| The Hidden Price of Streaming: Cutting Through the Options | Conceptual cost discussion |
| Databricks AI/BI Dashboard 2.0 | Feature announcement, duplicates aibi-dashboards skill |
| Juggling a Model Circus: A PyFunc's Guide to Multitenancy | Advanced ML pattern |
| Everything you ever wanted to know about DLT but were afraid to ask | Conceptual, duplicates spark-declarative-pipelines |
| PyFunc it well, Do it live | ML deployment, duplicates model-serving skill |
| Braving through the pitfalls of LLM Evaluation | ML evaluation, duplicates mlflow-evaluation skill |
| Databricks Vector Search similarity score | Specific feature, duplicates existing skills |
| How to actually delete data in Spark | Covered by delta-streaming-exactly-once |
| On the topic of LLMs and non-determinism | Conceptual discussion |
| Concurrent execution and query throughput | Advanced optimization |
| Archiving data in Databricks Lakehouse | Specific archival pattern |
| A Beginners Guide to MLOps Stacks | Conceptual overview |
| Spark file reads at warp speed | Advanced optimization |
| Deploying DeepSeek R1 Distill Qwen | Specific model deployment |
| Orchestrating Databricks Workflows | Covered by databricks-jobs skill |

### canadiandataguy.com (Skipped - 10 posts)

| Blog Title | Reason for Skipping |
|------------|---------------------|
| Unlocking Sub-Second Latency with Databricks | Video content, less actionable |
| I Knew the Answer. I Just Couldn't Remember It | Personal knowledge agent, conceptual |
| 4 Surprising Truths That Will Change How You Think About Spark Streaming | Conceptual overview |
| Why I Materialize Delta History for Debugging | Quick tip, too narrow |
| Stop Waiting for Connectors: Stream ANYTHING into Spark | Advanced streaming pattern |
| How to write your first Spark application with Stream-Stream Joins | Covered by spark-declarative-pipelines |
| Build an Ethereum ETL Pipeline for Free Using Databricks Free Edition | Specific use case (Ethereum) |
| How to ace and structure your Data Modelling Interview | Interview guidance, not technical skill |
| A Deep Dive into Skewed Joins, GroupBy Bottlenecks, and Smart Strategies | Covered by databricks-sql-warehouse-tuning |
| Decode the Join: A Spark Data Engineer's Visual Handbook | Conceptual overview |

---

## Skill Quality Checklist

All created skills meet the following criteria:

- [x] Valid YAML frontmatter with name, description, author, source_url, source_site
- [x] Description under 200 characters (frontmatter field)
- [x] Includes proper Attribution section
- [x] Contains at least one runnable code example
- [x] Self-contained content (no external dependencies)
- [x] Code blocks have language specifiers
- [x] No absolute file paths
- [x] Filename matches name field (SKILL.md in kebab-case directory)

---

## Repository Integration

- [x] Fork cloned: `https://github.com/jiteshsoni/ai-dev-kit.git`
- [x] Upstream remote added: `https://github.com/databricks-solutions/ai-dev-kit.git`
- [x] Branch created: `add-blog-skills`
- [x] All skills committed individually with conventional commit messages
- [x] Branch ready for push

## Notes

1. **Duplicate Detection**: Many blog posts covered concepts already present in existing skills (e.g., agent-bricks, databricks-jobs, model-serving). These were skipped to avoid duplication.

2. **Content Selection**: Priority was given to posts with:
   - Clear step-by-step instructions
   - Runnable code examples
   - Broad applicability
   - Technical depth appropriate for skills

3. **Attribution**: All skills include proper attribution in frontmatter and dedicated Attribution section.

4. **Quality Over Quantity**: 6 high-quality skills were preferred over converting all 53 posts, many of which were conceptual, duplicative, or too narrow in scope.
