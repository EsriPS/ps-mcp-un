### MongoDB Vector Search Pre-Filter

The `$vectorSearch` `filter` option matches BSON boolean, date, objectId, numeric, string, and UUID values, including arrays of these types.

You **must** index the fields that you want to filter your data by as the filter type in a vectorSearch type index definition. Filtering your data is useful to narrow the scope of your semantic search and ensure that not all vectors are considered for comparison.

MongoDB Vector Search supports the `$vectorSearch` `filter` option for the following MQL operators:

| Type    | MQL operator          |
| ------- | --------------------- |
| Equals  | `$eq`, `$ne`           |
| Range   | `$gt`, `$lt`, `$gte`, `$lte`  |
| In set  | `$in`, `$nin`             |
| Logical | `$not`, `$nor`, `$and`, `$or` |

## Note

The `$vectorSearch` `filter` option doesn't support other `query operators`, `aggregation pipeline operators`, or `MongoDB Search operators`.

#### Considerations
MongoDB Vector Search supports the short form of `$eq`. In the short form, you don't need to specify `$eq` in the query.

## Example

For example, consider the following filter with `$eq`:

This query will match documents by a metadata field named 'Customer_x0020_Number' with the value '757220':
```
"filter": { "metadata.Customer_x0020_Number": { "$eq":  "757220" } }
```

```
"filter": { "_id": { "$eq": ObjectId("5a9427648b0beebeb69537a5") }
```

You can run the preceding query using the short form of `$eq` in the following way:

```
"filter": { "_id": ObjectId("5a9427648b0beebeb69537a5") }
```

You can also specify an array of filters in a single query by using the `$and` operator.




## Example

For example, consider the following pre-filter for documents with a `genres` field equal to `Action` and a `year` field with the value `1999`, `2000`, or `2001`:

```
"filter": {  "$and": [    { "genres": "Action" },    { "year": { "$in": [ 1999, 2000, 2001 ] } }  ]}
```
