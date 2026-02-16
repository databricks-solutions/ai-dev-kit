# Synthetic Data Generation Skill Update Summary

## Summary of Changes

### SKILL.md Updates

1. **Added Generation Planning Workflow** (new section at top)
   - 3-step process: gather requirements, present table spec with assumptions, ask about data features
   - Pre-generation checklist for user approval
   - "Surprise Me" fallback option

2. **Updated Compute Selection**
   - Serverless-first with confirmation prompt
   - databricks-connect version guidance (>=15.1,<16.2 for Python 3.10/3.11; >=16.2 for Python 3.12)

3. **Replaced Data Generation Approaches**
   - **Option 1: Spark + Faker** (recommended for most cases, writing to UC)
   - **Option 2: Polars** (for local development, quick prototyping)
   - Removed dbldatagen as primary approach

4. **Added Deployment Options**
   - Ephemeral script run (default)
   - DABs bundle deployment with `client: "4"` for serverless

5. **Added Business Integrity Requirements**
   - Value coherence, tier behavior, temporal patterns, geographic patterns
   - Bad data injection patterns (nulls, outliers, duplicates, orphan FKs)

6. **Added Domain-Specific Guidance**
   - Retail/E-commerce, Support/CRM, Manufacturing/IoT, Financial Services

7. **Updated Complete Examples**
   - Example 1: E-commerce Data (Spark + Faker + Pandas)
   - Example 2: Local Development with Polars
   - Example 3: Large-Scale with Faker UDFs
   - Example 4: Legacy Approach (Faker + Pandas)

### Script Updates

| File | Action |
|------|--------|
| `scripts/generate_ecommerce_data.py` | Updated: serverless-first, bad data injection, incremental mode |
| `scripts/example_dbldatagen.py` | Deleted |
| `scripts/example_polars.py` | Created: local generation with Polars |
| `scripts/example_faker_udf.py` | Updated: serverless-first configuration |

## Key Decisions Implemented

1. **Serverless Default**: Yes, with user confirmation prompt
2. **databricks-connect Version**: >=15.1,<16.2 (Python 3.10/3.11) or >=16.2 (Python 3.12)
3. **Planning Phase**: Show table spec with assumptions before generating
4. **Templates**: Domain guidance (retail, manufacturing) without rigid schemas
5. **Incremental Mode**: Support `.mode("append")` for scheduled jobs
6. **Data Quality Features**: Bad data injection (nulls, outliers, duplicates, orphan FKs)
7. **NO dbldatagen by default**: Use Spark + Faker or Polars
8. **Deployment**: Both ephemeral scripts AND DABs bundles as options
