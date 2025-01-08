# Dump formats

The dumps should be only the data, not the structure of the database. They shoudl be `INSERT` statements,
not `COPY` statements. A data-only-dump in the correct format can be created with the following command:

```bash
pg_dump $DATABASE -a --no-owner --inserts > input/data.sql
```