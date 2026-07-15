# SDP Pipeline Configuration for DABs

## Key Decisions (prompt if unclear)
1. Streaming or batch oriented?
2. Continuous or triggered execution?
3. Serverless (default) or classic compute?

## Pipeline Resource Pattern

```yaml
resources:
  pipelines:
    pipeline_name:
      name: "[${bundle.target}] Pipeline Name"

      # Target catalog and schema
      catalog: ${var.catalog}
      target: ${var.schema}

      # Pipeline libraries
      libraries:
        - glob:
            include: ../src/pipelines/<pipeline_folder>/transformations/**
      
      root_path: ../src/pipelines/<pipeline_folder>

      serverless: true

      # Pipeline configuration
      configuration:
        source_catalog: ${var.source_catalog}
        source_schema: ${var.source_schema}

      continuous: false
      development: true
      photon: true

      channel: current

      permissions:
        - level: CAN_VIEW
          group_name: "users"
```

**Permission levels**: `CAN_VIEW`, `CAN_RUN`, `CAN_MANAGE`

## Best Practices

1. **Use `root_path` and `libraries.glob`** for newer organization structure
2. **Default to serverless** unless user specifies otherwise
3. **Use variables** for catalog/schema parameterization
4. **Set `development: true`** for dev/staging targets
