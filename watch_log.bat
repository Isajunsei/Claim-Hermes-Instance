@echo off
for /f "delims=" %%i in ('gh run list --repo Isajunsei/Claim-Hermes-Instance --status in_progress --json databaseId --jq ".[0].databaseId"') do set RUN_ID=%%i
echo Run ID: %RUN_ID%
start https://github.com/Isajunsei/Claim-Hermes-Instance/actions/runs/%RUN_ID%
