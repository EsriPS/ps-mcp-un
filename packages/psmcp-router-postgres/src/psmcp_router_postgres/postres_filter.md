### Postgres Vector Search Pre-Filter

The `$vectorSearch` `filter` option matches BSON boolean, date, objectId, numeric, string, and UUID values, including arrays of these types.

You **must** index the fields that you want to filter your data by as the filter type in a vectorSearch type index definition. Filtering your data is useful to narrow the scope of your semantic search and ensure that not all vectors are considered for comparison.

Vector Search supports the `$vectorSearch` `filter` option for the following MQL operators:

| Type    | Operator                      |
| ------- |-------------------------------|
| Equals  | `$eq`, `$ne`                  |
| Range   | `$gt`, `$lt`, `$gte`, `$lte`  |
| In set  | `$in`, `$nin`                 |
| Logical | `$not`, `$nor`, `$and`, `$or` |


## Example

For example, consider the following filter with `$eq`:

This query will match documents by a metadata field named 'Customer_x0020_Number' with the value '757220':
```
"filter": { "metadata.Customer_x0020_Number": { "$eq":  "757220" } }
```

```
"filter": { "_id": { "$eq": ObjectId("5a9427648b0beebeb69537a5") }
```

#### Considerations
Vector Search supports the short form of `$eq`. In the short form, you don't need to specify `$eq` in the query.

You can run the preceding query using the short form of `$eq` in the following way:

```
"filter": { "_id": ObjectId("5a9427648b0beebeb69537a5") }
```

You can also specify an array of filters in a single query by using the `$and` operator.

## Example

The user asks for 'all documents with site id 1234':
```
"filter": { "$and": [ { "site_id": 1234 } ] }, "query": ""
```


## Example

For example, consider the following filter for documents with a `genres` field equal to `Action` and a `year` field with the value `1999`, `2000`, or `2001`:

```
"filter": {  "$and": [    { "genres": "Action" },    { "year": { "$in": [ 1999, 2000, 2001 ] } }  ]}
```

## Extent Example
If a user asks for all documents overlapping certain geographic bounds:
Use something like the following filter for documents with extents that **overlap** the specified geographic bounds.

For two bounding boxes to overlap, each box must start before the other ends on both axes.

Given a query extent of `xmin=44, ymin=-23, xmax=45, ymax=-22`:

```
"filter": {
  "$and": [
    { "extent_xmin": { "$lte": 45 } },
    { "extent_xmax": { "$gte": 44 } },
    { "extent_ymin": { "$lte": -22 } },
    { "extent_ymax": { "$gte": -23 } }
  ]
}
```

The logic is:
- Document's `extent_xmin` ≤ Query's `xmax` (document starts before query ends horizontally)
- Document's `extent_xmax` ≥ Query's `xmin` (document ends after query starts horizontally)
- Document's `extent_ymin` ≤ Query's `ymax` (document starts before query ends vertically)
- Document's `extent_ymax` ≥ Query's `ymin` (document ends after query starts vertically)
## Best Practices

1. **Use Indexed Columns**: Filter on columns that have indexes for better performance
2. **Specificity**: More specific filters reduce the search space and improve speed
3. **Type Matching**: Ensure data types match (use quotes for strings, proper date formats, etc.)

## Performance Tips

- Filters are applied BEFORE vector similarity calculation
- Using indexed columns in filter objects dramatically improves performance
- Combining multiple filter conditions can narrow results effectively
- Consider creating indexes on frequently filtered columns