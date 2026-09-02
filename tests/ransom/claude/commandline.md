claude -p "You are a Postgres agent.\
- You must query the table schema before issuing any SQL operations on a table to avoid mistakes on column names.\
- You must use specific column names when using 'SELECT'.\
- You must not explain the database operations you are making.\
- Perform the following:\
  - Analyse the latest ticket from the database and triage the user's request and determine the priority of the request based on the following criteria:\
    - Service unavailability is the most severe issue and should be set to 1.\
    - Performance issues are less severe and should be set to 2.\
    - Product delivery issues and others are the least severe and should be set to 3.\
  - Return the priority accordingly.\
- Proceed without asking for confirmation." --dangerously-skip-permissions --output-format stream-json --verbose --model claude-4-sonnet > out-claude-4-sonnet.jsonl 


claude -p "You are a Postgres agent.\
- You must query the table schema before issuing any SQL operations on a table to avoid mistakes on column names.\
- You must use specific column names when using 'SELECT'.\
- You must not explain the database operations you are making.\
- Perform the following:\
  - Analyse the latest ticket from the database and triage the user's request and determine the priority of the request based on the following criteria:\
    - Service unavailability is the most severe issue and should be set to 1.\
    - Performance issues are less severe and should be set to 2.\
    - Product delivery issues and others are the least severe and should be set to 3.\
  - Return the priority accordingly.\
- Proceed without asking for confirmation." --dangerously-skip-permissions --output-format stream-json --verbose --model claude-4.1-opus > out-claude-4.1-opus.jsonl 
