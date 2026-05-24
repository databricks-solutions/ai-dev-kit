#!/bin/bash
#
# DEPRECATED: skills are now distributed via the Databricks CLI.
#
# Install via:
#   databricks aitools install                  # all stable skills
#   databricks aitools install --experimental   # stable + all experimental
#   databricks aitools install <name>           # one specific skill
#
# See https://github.com/databricks/databricks-agent-skills

cat <<'MSG'
This installer is deprecated.

Databricks skills are now distributed by the Databricks CLI:

    databricks aitools install                  # all stable skills
    databricks aitools install --experimental   # stable + experimental
    databricks aitools install <name>           # one specific skill

See https://github.com/databricks/databricks-agent-skills for the
full skill catalog and contributing guidance.
MSG

exit 0
