# Geospatial SQL and Collations in Databricks SQL

---

## Part 1: Geospatial SQL

Databricks SQL provides comprehensive geospatial support through two function families: **H3 functions** for hexagonal grid indexing and **ST functions** for standard spatial operations. Together they enable high-performance geospatial analytics at scale.

### Geospatial Data Types

| Type | Description | Coordinate System | SRID Support |
|------|-------------|-------------------|--------------|
| `GEOMETRY` | Spatial objects using Euclidean coordinates (X, Y, optional Z) -- treats Earth as flat | Any projected CRS | 11,000+ SRIDs |
| `GEOGRAPHY` | Geographic objects on Earth's surface using longitude/latitude | WGS 84 | SRID 4326 only |

**When to use which:**
- Use `GEOMETRY` for projected coordinate systems, Euclidean distance calculations, and when working with local/regional data in meters or feet.
- Use `GEOGRAPHY` for global data using longitude/latitude coordinates and spherical distance calculations.

### Supported Geometry Subtypes

Both `GEOMETRY` and `GEOGRAPHY` support: **Point**, **LineString**, **Polygon**, **MultiPoint**, **MultiLineString**, **MultiPolygon**, and **GeometryCollection**.

### Format Support

| Format | Description | Import Function | Export Function |
|--------|-------------|-----------------|-----------------|
| WKT | Well-Known Text | `ST_GeomFromWKT`, `ST_GeogFromWKT` | `ST_AsWKT`, `ST_AsText` |
| WKB | Well-Known Binary | `ST_GeomFromWKB`, `ST_GeogFromWKB` | `ST_AsWKB`, `ST_AsBinary` |
| EWKT | Extended WKT (includes SRID) | `ST_GeomFromEWKT`, `ST_GeogFromEWKT` | `ST_AsEWKT` |
| EWKB | Extended WKB (includes SRID) | `ST_GeomFromEWKB` | `ST_AsEWKB` |
| GeoJSON | JSON-based format | `ST_GeomFromGeoJSON`, `ST_GeogFromGeoJSON` | `ST_AsGeoJSON` |
| Geohash | Hierarchical grid encoding | `ST_GeomFromGeoHash`, `ST_PointFromGeoHash` | `ST_GeoHash` |

---

### H3 Geospatial Functions

H3 is Uber's hexagonal hierarchical spatial index. It divides the Earth into hexagonal cells at 16 resolutions (0-15). Available since Databricks Runtime 11.2 (H3 Java library 3.7.0). No separate installation required.

#### H3 Import Functions (Coordinate/Geometry to H3)

| Function | Description | Returns |
|----------|-------------|---------|
| `h3_longlatash3(lon, lat, resolution)` | Convert longitude/latitude to H3 cell ID | `BIGINT` |
| `h3_longlatash3string(lon, lat, resolution)` | Convert longitude/latitude to H3 cell ID | `STRING` (hex) |
| `h3_pointash3(geogExpr, resolution)` | Convert GEOGRAPHY point to H3 cell ID | `BIGINT` |
| `h3_pointash3string(geogExpr, resolution)` | Convert GEOGRAPHY point to H3 cell ID | `STRING` (hex) |
| `h3_polyfillash3(geogExpr, resolution)` | Fill polygon with contained H3 cells | `ARRAY<BIGINT>` |
| `h3_polyfillash3string(geogExpr, resolution)` | Fill polygon with contained H3 cells | `ARRAY<STRING>` |
| `h3_coverash3(geogExpr, resolution)` | Cover geography with minimal set of H3 cells | `ARRAY<BIGINT>` |
| `h3_coverash3string(geogExpr, resolution)` | Cover geography with minimal set of H3 cells | `ARRAY<STRING>` |
| `h3_tessellateaswkb(geogExpr, resolution)` | Tessellate geography using H3 cells | `ARRAY<STRUCT>` |
| `h3_try_polyfillash3(geogExpr, resolution)` | Safe polyfill (returns NULL on error) | `ARRAY<BIGINT>` |
| `h3_try_polyfillash3string(geogExpr, resolution)` | Safe polyfill (returns NULL on error) | `ARRAY<STRING>` |
| `h3_try_coverash3(geogExpr, resolution)` | Safe cover (returns NULL on error) | `ARRAY<BIGINT>` |
| `h3_try_coverash3string(geogExpr, resolution)` | Safe cover (returns NULL on error) | `ARRAY<STRING>` |
| `h3_try_tessellateaswkb(geogExpr, resolution)` | Safe tessellate (returns NULL on error) | `ARRAY<STRUCT>` |

#### H3 Export Functions (H3 to Geometry/Format)

| Function | Description | Returns |
|----------|-------------|---------|
| `h3_boundaryaswkt(h3CellId)` | H3 cell boundary as WKT polygon | `STRING` |
| `h3_boundaryaswkb(h3CellId)` | H3 cell boundary as WKB polygon | `BINARY` |
| `h3_boundaryasgeojson(h3CellId)` | H3 cell boundary as GeoJSON | `STRING` |
| `h3_centeraswkt(h3CellId)` | H3 cell center as WKT point | `STRING` |
| `h3_centeraswkb(h3CellId)` | H3 cell center as WKB point | `BINARY` |
| `h3_centerasgeojson(h3CellId)` | H3 cell center as GeoJSON point | `STRING` |

#### H3 Conversion Functions

| Function | Description |
|----------|-------------|
| `h3_h3tostring(h3CellId)` | Convert BIGINT cell ID to hex STRING |
| `h3_stringtoh3(h3CellIdString)` | Convert hex STRING to BIGINT cell ID |

#### H3 Hierarchy / Traversal Functions

| Function | Description |
|----------|-------------|
| `h3_resolution(h3CellId)` | Get the resolution of a cell |
| `h3_toparent(h3CellId, resolution)` | Get parent cell at coarser resolution |
| `h3_tochildren(h3CellId, resolution)` | Get all child cells at finer resolution |
| `h3_maxchild(h3CellId, resolution)` | Get child with maximum value |
| `h3_minchild(h3CellId, resolution)` | Get child with minimum value |
| `h3_ischildof(h3CellId1, h3CellId2)` | Test if cell1 is equal to or child of cell2 |

#### H3 Distance / Neighbor Functions

| Function | Description |
|----------|-------------|
| `h3_distance(h3CellId1, h3CellId2)` | Grid distance between two cells |
| `h3_try_distance(h3CellId1, h3CellId2)` | Grid distance or NULL if undefined |
| `h3_kring(h3CellId, k)` | All cells within grid distance k (filled disk) |
| `h3_kringdistances(h3CellId, k)` | Cells within distance k with their distances |
| `h3_hexring(h3CellId, k)` | Hollow ring of cells at exactly distance k |

#### H3 Compaction Functions

| Function | Description |
|----------|-------------|
| `h3_compact(h3CellIds)` | Compact array of cells to minimal representation |
| `h3_uncompact(h3CellIds, resolution)` | Expand compacted cells to target resolution |

#### H3 Validation Functions

| Function | Description |
|----------|-------------|
| `h3_isvalid(expr)` | Check if BIGINT or STRING is valid H3 cell |
| `h3_validate(h3CellId)` | Return cell ID if valid, error otherwise |
| `h3_try_validate(h3CellId)` | Return cell ID if valid, NULL otherwise |
| `h3_ispentagon(h3CellId)` | Check if cell is a pentagon (12 per resolution) |

#### H3 Examples

```sql
-- Convert coordinates to H3 cell at resolution 9
SELECT h3_longlatash3(-73.985428, 40.748817, 9) AS h3_cell;

-- Index taxi trips by pickup location
CREATE TABLE trips_h3 AS
SELECT
  h3_longlatash3(pickup_longitude, pickup_latitude, 12) AS pickup_cell,
  h3_longlatash3(dropoff_longitude, dropoff_latitude, 12) AS dropoff_cell,
  *
FROM taxi_trips;

-- Fill zip code polygons with H3 cells for spatial indexing
CREATE TABLE zipcode_h3 AS
SELECT
  explode(h3_polyfillash3(geom_wkt, 12)) AS cell,
  zipcode, city, state
FROM zipcodes;

-- Find all trips picked up in a specific zip code using H3 join
SELECT t.*
FROM trips_h3 t
INNER JOIN zipcode_h3 z ON t.pickup_cell = z.cell
WHERE z.zipcode = '10001';

-- Proximity search: find all H3 cells within 2 rings of a location
SELECT explode(h3_kring(h3_longlatash3(-73.985, 40.748, 9), 2)) AS nearby_cell;

-- Aggregate trip counts and get centroids for visualization
SELECT
  dropoff_cell,
  h3_centerasgeojson(dropoff_cell):coordinates[0] AS lon,
  h3_centerasgeojson(dropoff_cell):coordinates[1] AS lat,
  count(*) AS trip_count
FROM trips_h3
GROUP BY dropoff_cell;

-- Roll up to coarser resolution
SELECT
  h3_toparent(pickup_cell, 7) AS parent_cell,
  count(*) AS trip_count
FROM trips_h3
GROUP BY h3_toparent(pickup_cell, 7);

-- Compact a set of cells for efficient storage
SELECT h3_compact(collect_set(cell)) AS compacted
FROM zipcode_h3
WHERE zipcode = '10001';
```

---

### ST Geospatial Functions

Native spatial SQL functions operating on `GEOMETRY` and `GEOGRAPHY` types. Requires Databricks Runtime 17.1+. Public Preview. Over 80 functions available.

#### ST Import Functions (Create Geometry/Geography)

| Function | Description | Output Type |
|----------|-------------|-------------|
| `ST_GeomFromText(wkt [, srid])` | Create GEOMETRY from WKT | `GEOMETRY` |
| `ST_GeomFromWKT(wkt [, srid])` | Create GEOMETRY from WKT (alias) | `GEOMETRY` |
| `ST_GeomFromWKB(wkb [, srid])` | Create GEOMETRY from WKB | `GEOMETRY` |
| `ST_GeomFromEWKT(ewkt)` | Create GEOMETRY from Extended WKT | `GEOMETRY` |
| `ST_GeomFromEWKB(ewkb)` | Create GEOMETRY from Extended WKB | `GEOMETRY` |
| `ST_GeomFromGeoJSON(geojson)` | Create GEOMETRY(4326) from GeoJSON | `GEOMETRY` |
| `ST_GeomFromGeoHash(geohash)` | Create polygon GEOMETRY from geohash | `GEOMETRY` |
| `ST_GeogFromText(wkt)` | Create GEOGRAPHY(4326) from WKT | `GEOGRAPHY` |
| `ST_GeogFromWKT(wkt)` | Create GEOGRAPHY(4326) from WKT | `GEOGRAPHY` |
| `ST_GeogFromWKB(wkb)` | Create GEOGRAPHY(4326) from WKB | `GEOGRAPHY` |
| `ST_GeogFromEWKT(ewkt)` | Create GEOGRAPHY from Extended WKT | `GEOGRAPHY` |
| `ST_GeogFromGeoJSON(geojson)` | Create GEOGRAPHY(4326) from GeoJSON | `GEOGRAPHY` |
| `ST_Point(x, y [, srid])` | Create point from coordinates | `GEOMETRY` |
| `ST_PointFromGeoHash(geohash)` | Create point from geohash center | `GEOMETRY` |
| `to_geometry(georepExpr)` | Auto-detect format and create GEOMETRY | `GEOMETRY` |
| `to_geography(georepExpr)` | Auto-detect format and create GEOGRAPHY | `GEOGRAPHY` |
| `try_to_geometry(georepExpr)` | Safe geometry creation (NULL on error) | `GEOMETRY` |
| `try_to_geography(georepExpr)` | Safe geography creation (NULL on error) | `GEOGRAPHY` |

#### ST Export Functions

| Function | Description | Output |
|----------|-------------|--------|
| `ST_AsText(geo)` | Export as WKT | `STRING` |
| `ST_AsWKT(geo)` | Export as WKT (alias) | `STRING` |
| `ST_AsBinary(geo)` | Export as WKB | `BINARY` |
| `ST_AsWKB(geo)` | Export as WKB (alias) | `BINARY` |
| `ST_AsEWKT(geo)` | Export as Extended WKT | `STRING` |
| `ST_AsEWKB(geo)` | Export as Extended WKB | `BINARY` |
| `ST_AsGeoJSON(geo)` | Export as GeoJSON | `STRING` |
| `ST_GeoHash(geo)` | Export as geohash string | `STRING` |

#### ST Constructor Functions

| Function | Description |
|----------|-------------|
| `ST_Point(x, y [, srid])` | Create a point geometry |
| `ST_MakeLine(pointArray)` | Create linestring from array of points |
| `ST_MakePolygon(outer [, innerArray])` | Create polygon from outer ring and optional holes |

#### ST Accessor Functions

| Function | Description | Returns |
|----------|-------------|---------|
| `ST_X(geo)` | X coordinate of a point | `DOUBLE` |
| `ST_Y(geo)` | Y coordinate of a point | `DOUBLE` |
| `ST_Z(geo)` | Z coordinate of a point | `DOUBLE` |
| `ST_M(geo)` | M coordinate of a point | `DOUBLE` |
| `ST_XMin(geo)` | Minimum X of bounding box | `DOUBLE` |
| `ST_XMax(geo)` | Maximum X of bounding box | `DOUBLE` |
| `ST_YMin(geo)` | Minimum Y of bounding box | `DOUBLE` |
| `ST_YMax(geo)` | Maximum Y of bounding box | `DOUBLE` |
| `ST_ZMin(geo)` | Minimum Z coordinate | `DOUBLE` |
| `ST_ZMax(geo)` | Maximum Z coordinate | `DOUBLE` |
| `ST_Dimension(geo)` | Topological dimension (0=point, 1=line, 2=polygon) | `INT` |
| `ST_NDims(geo)` | Number of coordinate dimensions | `INT` |
| `ST_NPoints(geo)` | Total number of points | `INT` |
| `ST_NumGeometries(geo)` | Number of geometries in collection | `INT` |
| `ST_NumInteriorRings(geo)` | Number of interior rings (polygon) | `INT` |
| `ST_GeometryType(geo)` | Geometry type as string | `STRING` |
| `ST_GeometryN(geo, n)` | N-th geometry (1-based) from collection | `GEOMETRY` |
| `ST_PointN(geo, n)` | N-th point from linestring | `GEOMETRY` |
| `ST_StartPoint(geo)` | First point of linestring | `GEOMETRY` |
| `ST_EndPoint(geo)` | Last point of linestring | `GEOMETRY` |
| `ST_ExteriorRing(geo)` | Outer ring of polygon | `GEOMETRY` |
| `ST_InteriorRingN(geo, n)` | N-th interior ring of polygon | `GEOMETRY` |
| `ST_Envelope(geo)` | Minimum bounding rectangle | `GEOMETRY` |
| `ST_Envelope_Agg(geo)` | Aggregate: bounding box of all geometries | `GEOMETRY` |
| `ST_Dump(geo)` | Explode multi-geometry into array of singles | `ARRAY` |
| `ST_IsEmpty(geo)` | True if geometry has no points | `BOOLEAN` |

#### ST Measurement Functions

| Function | Description |
|----------|-------------|
| `ST_Area(geo)` | Area of a polygon (in CRS units) |
| `ST_Length(geo)` | Length of a linestring (in CRS units) |
| `ST_Perimeter(geo)` | Perimeter of a polygon (in CRS units) |
| `ST_Distance(geo1, geo2)` | Cartesian distance between geometries |
| `ST_DistanceSphere(geo1, geo2)` | Spherical distance in meters (fast, approximate) |
| `ST_DistanceSpheroid(geo1, geo2)` | Geodesic distance in meters on WGS84 (accurate) |
| `ST_Azimuth(geo1, geo2)` | North-based azimuth angle in radians |
| `ST_ClosestPoint(geo1, geo2)` | Point on geo1 closest to geo2 |

#### ST Topological Relationship Functions (Predicates)

| Function | Description |
|----------|-------------|
| `ST_Contains(geo1, geo2)` | True if geo1 fully contains geo2 |
| `ST_Within(geo1, geo2)` | True if geo1 is fully within geo2 (inverse of Contains) |
| `ST_Intersects(geo1, geo2)` | True if geometries share any space |
| `ST_Disjoint(geo1, geo2)` | True if geometries share no space |
| `ST_Touches(geo1, geo2)` | True if boundaries touch but interiors do not |
| `ST_Covers(geo1, geo2)` | True if geo1 covers geo2 (no point of geo2 is exterior) |
| `ST_Equals(geo1, geo2)` | True if geometries are topologically equal |
| `ST_DWithin(geo1, geo2, distance)` | True if geometries are within given distance |

#### ST Overlay Functions (Set Operations)

| Function | Description |
|----------|-------------|
| `ST_Intersection(geo1, geo2)` | Geometry of shared space |
| `ST_Union(geo1, geo2)` | Geometry combining both inputs |
| `ST_Union_Agg(geo)` | Aggregate: union of all geometries in column |
| `ST_Difference(geo1, geo2)` | Geometry of geo1 minus geo2 |

#### ST Processing Functions

| Function | Description |
|----------|-------------|
| `ST_Buffer(geo, radius)` | Expand geometry by radius distance |
| `ST_Centroid(geo)` | Center point of geometry |
| `ST_ConvexHull(geo)` | Smallest convex polygon containing geometry |
| `ST_ConcaveHull(geo, ratio [, allowHoles])` | Concave hull with length ratio |
| `ST_Boundary(geo)` | Boundary of geometry (not available on all SQL Warehouse versions) |
| `ST_Simplify(geo, tolerance)` | Simplify using Douglas-Peucker algorithm |

#### ST Editor Functions

| Function | Description |
|----------|-------------|
| `ST_AddPoint(linestring, point [, index])` | Add point to linestring |
| `ST_RemovePoint(linestring, index)` | Remove point from linestring |
| `ST_SetPoint(linestring, index, point)` | Replace point in linestring |
| `ST_FlipCoordinates(geo)` | Swap X and Y coordinates |
| `ST_Multi(geo)` | Convert single geometry to multi-geometry |
| `ST_Reverse(geo)` | Reverse vertex order |

#### ST Affine Transformation Functions

| Function | Description |
|----------|-------------|
| `ST_Translate(geo, xOffset, yOffset [, zOffset])` | Move geometry by offset |
| `ST_Scale(geo, xFactor, yFactor [, zFactor])` | Scale geometry by factors |
| `ST_Rotate(geo, angle)` | Rotate geometry around origin (radians) |

#### ST Spatial Reference System Functions

| Function | Description |
|----------|-------------|
| `ST_SRID(geo)` | Get SRID of geometry |
| `ST_SetSRID(geo, srid)` | Set SRID value (no reprojection) |
| `ST_Transform(geo, targetSrid)` | Reproject to target coordinate system |

#### ST Validation

| Function | Description |
|----------|-------------|
| `ST_IsValid(geo)` | Check if geometry is OGC-valid |

#### ST Practical Examples

> **Note:** `GEOMETRY` and `GEOGRAPHY` column types in `CREATE TABLE` require serverless compute with DBR 17.1+. On SQL Warehouses that don't support these column types, use `STRING` columns with WKT representation and convert with `ST_GeomFromText()` / `ST_GeogFromText()` at query time.

```sql
-- Create a table with geometry columns (requires serverless DBR 17.1+)
CREATE TABLE retail_stores (
  store_id INT,
  name STRING,
  location GEOMETRY
);

INSERT INTO retail_stores VALUES
  (1, 'Downtown Store', ST_Point(-73.9857, 40.7484, 4326)),
  (2, 'Midtown Store',  ST_Point(-73.9787, 40.7614, 4326)),
  (3, 'Uptown Store',   ST_Point(-73.9680, 40.7831, 4326));

-- Create delivery zones as polygons
CREATE TABLE delivery_zones (
  zone_id INT,
  zone_name STRING,
  boundary GEOMETRY
);

INSERT INTO delivery_zones VALUES
  (1, 'Zone A', ST_GeomFromText(
    'POLYGON((-74.00 40.74, -73.97 40.74, -73.97 40.76, -74.00 40.76, -74.00 40.74))', 4326
  ));

-- Point-in-polygon: find stores within a delivery zone
SELECT s.name, z.zone_name
FROM retail_stores s
JOIN delivery_zones z
  ON ST_Contains(z.boundary, s.location);

-- Distance calculation: find customers within 5km of a store
-- Note: to_geography() expects STRING (WKT/GeoJSON) or BINARY (WKB) input, not GEOMETRY.
-- Use ST_AsText() to convert GEOMETRY to WKT first.
SELECT c.customer_id, c.name,
  ST_DistanceSphere(c.location, s.location) AS distance_meters
FROM customers c
CROSS JOIN retail_stores s
WHERE s.store_id = 1
  AND ST_DWithin(
    ST_GeogFromText(ST_AsText(c.location)),
    ST_GeogFromText(ST_AsText(s.location)),
    5000  -- 5km in meters
  );

-- Buffer zone: create 1km buffer around a store (use projected CRS for meters)
SELECT ST_Buffer(
  ST_Transform(location, 5070),  -- project to NAD83/Albers (meters)
  1000                            -- 1000 meters
) AS buffer_zone
FROM retail_stores
WHERE store_id = 1;

-- Area calculation
SELECT zone_name,
  ST_Area(ST_Transform(boundary, 5070)) AS area_sq_meters
FROM delivery_zones;

-- Union of overlapping zones
SELECT ST_Union_Agg(boundary) AS combined_coverage
FROM delivery_zones;

-- Convert between formats
SELECT
  ST_AsText(location) AS wkt,
  ST_AsGeoJSON(location) AS geojson,
  ST_GeoHash(location) AS geohash
FROM retail_stores;

-- Spatial join with BROADCAST hint for performance
SELECT /*+ BROADCAST(zones) */
  c.customer_id, z.zone_name
FROM customers c
JOIN delivery_zones zones
  ON ST_Contains(zones.boundary, c.location);
```

### Combining H3 and ST Functions

```sql
-- Use H3 for fast pre-filtering, then ST for precise spatial operations
-- Step 1: Index store locations with H3
CREATE TABLE store_h3 AS
SELECT store_id, name, location,
  h3_longlatash3(ST_X(location), ST_Y(location), 9) AS h3_cell
FROM retail_stores;

-- Step 2: Index customer locations with H3
CREATE TABLE customer_h3 AS
SELECT customer_id, name, location,
  h3_longlatash3(ST_X(location), ST_Y(location), 9) AS h3_cell
FROM customers;

-- Step 3: Fast proximity using H3 pre-filter + precise ST distance
SELECT s.name AS store, c.name AS customer,
  ST_DistanceSphere(s.location, c.location) AS distance_m
FROM store_h3 s
JOIN customer_h3 c
  ON c.h3_cell IN (SELECT explode(h3_kring(s.h3_cell, 2)))
WHERE ST_DistanceSphere(s.location, c.location) < 2000;
```

### Spatial Join Performance

Databricks automatically optimizes spatial joins using built-in spatial indexing. Spatial predicates like `ST_Intersects`, `ST_Contains`, and `ST_Within` in JOIN conditions benefit from up to **17x performance improvement** compared to classic clusters. No code changes required -- the optimizer applies spatial indexing automatically.

**Performance tips:**
- Use `BROADCAST` hint when one side of the join is small enough to fit in memory.
- Use projected coordinate systems (e.g., SRID 5070 in meters) for distance calculations to avoid expensive spheroid functions.
- Combine H3 for coarse pre-filtering with ST for precise operations.
- Use Delta Lake liquid clustering on H3 cell columns for optimized data layout.
- Enable auto-optimization: `delta.autoOptimize.optimizeWrite` and `delta.autoOptimize.autoCompact`.

---

## Part 2: Collations

Collations define rules for comparing and sorting strings. Databricks supports binary, case-insensitive, accent-insensitive, and locale-specific collations using the ICU library. Available from Databricks Runtime 16.1+.

### Collation Types

| Collation | Description | Behavior |
|-----------|-------------|----------|
| `UTF8_BINARY` | Default. Byte-by-byte comparison of UTF-8 encoding | `'A' < 'Z' < 'a'` -- binary order, case/accent sensitive |
| `UTF8_LCASE` | Case-insensitive binary. Converts to lowercase then compares with UTF8_BINARY | `'A' == 'a'` but `'e' != 'e'` (accent sensitive) |
| `UNICODE` | ICU root locale. Language-agnostic Unicode ordering | `'a' < 'A' < 'A' < 'b'` -- groups similar characters |
| Locale-specific | ICU locale-based (e.g., `DE`, `FR`, `JA`) | Language-aware sorting rules |

### Collation Syntax

```
{ UTF8_BINARY | UTF8_LCASE | { UNICODE | locale } [ _ modifier [...] ] }
```

Where `locale` is:
```
language_code [ _ script_code ] [ _ country_code ]
```

- `language_code`: ISO 639-1 (e.g., `EN`, `DE`, `FR`, `JA`, `ZH`)
- `script_code`: ISO 15924 (e.g., `Hant` for Traditional Chinese, `Latn` for Latin)
- `country_code`: ISO 3166-1 (e.g., `US`, `DE`, `CAN`)

### Collation Modifiers (DBR 16.2+)

| Modifier | Description | Default |
|----------|-------------|---------|
| `CS` | Case-Sensitive: `'A' != 'a'` | Yes (default) |
| `CI` | Case-Insensitive: `'A' == 'a'` | No |
| `AS` | Accent-Sensitive: `'e' != 'e'` | Yes (default) |
| `AI` | Accent-Insensitive: `'e' == 'e'` | No |
| `RTRIM` | Trailing-space insensitive: `'Hello' == 'Hello '` | No |

Specify at most one from each pair (CS/CI, AS/AI) plus optional RTRIM. Order does not matter.

### Locale Examples

| Collation Name | Description |
|----------------|-------------|
| `UNICODE` | ICU root locale, language-agnostic |
| `UNICODE_CI` | Unicode, case-insensitive |
| `UNICODE_CI_AI` | Unicode, case and accent-insensitive |
| `DE` | German sorting rules |
| `DE_CI_AI` | German, case and accent-insensitive |
| `FR_CAN` | French (Canada) |
| `EN_US` | English (United States) |
| `ZH_Hant_MAC` | Traditional Chinese (Macau) |
| `SR` | Serbian (normalized from `SR_CYR_SRN_CS_AS`) |
| `JA` | Japanese |
| `EN_CS_AI` | English, case-sensitive, accent-insensitive |
| `UTF8_LCASE_RTRIM` | Case-insensitive with trailing space trimming |

### Collation Precedence

From highest to lowest:

1. **Explicit** -- Assigned via `COLLATE` expression
2. **Implicit** -- Derived from column, field, or variable definition
3. **Default** -- Applied to string literals and function results
4. **None** -- When combining different implicit collations

Mixing two different **explicit** collations in the same expression produces an error.

### Setting Collations at Different Levels

#### Catalog Level (DBR 17.1+)

```sql
-- Create catalog with default collation
CREATE CATALOG customer_cat
  DEFAULT COLLATION UNICODE_CI_AI;

-- All schemas, tables, and string columns created in this catalog
-- inherit UNICODE_CI_AI unless overridden
```

#### Schema Level (DBR 17.1+)

```sql
-- Create schema with default collation
CREATE SCHEMA my_schema
  DEFAULT COLLATION UNICODE_CI;

-- Change default collation for new objects (existing objects unchanged)
ALTER SCHEMA my_schema
  DEFAULT COLLATION UNICODE_CI_AI;
```

#### Table Level (DBR 16.3+)

```sql
-- Table-level default collation
CREATE TABLE users (
  id INT,
  username STRING,           -- inherits UNICODE_CI from table default
  email STRING,              -- inherits UNICODE_CI from table default
  password_hash STRING COLLATE UTF8_BINARY  -- explicit override
) DEFAULT COLLATION UNICODE_CI;
```

#### Column Level (DBR 16.1+)

```sql
-- Column-level collation
CREATE TABLE products (
  id INT,
  name STRING COLLATE UNICODE_CI,
  sku STRING COLLATE UTF8_BINARY,
  description STRING COLLATE UNICODE_CI_AI
);

-- Add column with collation
ALTER TABLE products
  ADD COLUMN category STRING COLLATE UNICODE_CI;

-- Change column collation (requires DBR 17.2+; may not be available on all SQL Warehouse versions)
ALTER TABLE products
  ALTER COLUMN name SET COLLATION UNICODE_CI_AI;
```

#### Expression Level

```sql
-- Apply collation inline in a query
SELECT *
FROM products
WHERE name COLLATE UNICODE_CI = 'laptop';

-- Check the collation of an expression
SELECT collation('test' COLLATE UNICODE_CI);
-- Returns: UNICODE_CI
```

### Collation Inheritance Hierarchy

```
Catalog DEFAULT COLLATION
  -> Schema DEFAULT COLLATION (overrides catalog)
    -> Table DEFAULT COLLATION (overrides schema)
      -> Column COLLATE (overrides table)
        -> Expression COLLATE (overrides column)
```

If no collation is specified at any level, `UTF8_BINARY` is used.

### Collation-Aware String Functions

Most string functions respect collations. Key collation-aware operations:

| Function/Operator | Collation Behavior |
|-------------------|-------------------|
| `=`, `!=`, `<`, `>`, `<=`, `>=` | Comparison uses column/expression collation |
| `LIKE` | Pattern matching respects collation |
| `CONTAINS(str, substr)` | Substring search respects collation |
| `STARTSWITH(str, prefix)` | Prefix match respects collation |
| `ENDSWITH(str, suffix)` | Suffix match respects collation |
| `IN (...)` | Membership test respects collation |
| `BETWEEN` | Range comparison respects collation |
| `ORDER BY` | Sorting respects collation |
| `GROUP BY` | Grouping respects collation |
| `DISTINCT` | Deduplication respects collation |
| `REPLACE(str, old, new)` | Search respects collation |
| `TRIM` / `LTRIM` / `RTRIM` | Trim characters respect collation |

**Performance note:** `STARTSWITH` and `ENDSWITH` with `UTF8_LCASE` collation show up to **10x performance speedup** compared to equivalent `LOWER()` workarounds.

### Utility Functions

```sql
-- Get collation of an expression
SELECT collation(name) FROM products;

-- List all supported collations
SELECT * FROM collations();

-- Test collation with COLLATE
SELECT collation('hello' COLLATE DE_CI_AI);
-- Returns: DE_CI_AI
```

### Practical Collation Examples

#### Case-Insensitive Search

```sql
-- Using column collation (preferred - leverages indexes)
CREATE TABLE users (
  id INT,
  username STRING COLLATE UTF8_LCASE,
  email STRING COLLATE UTF8_LCASE
);

INSERT INTO users VALUES
  (1, 'JohnDoe', 'John@Example.com'),
  (2, 'janedoe', 'JANE@EXAMPLE.COM');

-- Case-insensitive match automatically
SELECT * FROM users WHERE username = 'johndoe';
-- Returns: JohnDoe

SELECT * FROM users WHERE email = 'john@example.com';
-- Returns: John@Example.com
```

#### Case-Insensitive Search with Expression Collation

```sql
-- Ad-hoc case-insensitive comparison on a UTF8_BINARY column
SELECT * FROM products
WHERE name COLLATE UNICODE_CI = 'MacBook Pro';
-- Matches: macbook pro, MACBOOK PRO, MacBook Pro, etc.
```

#### Accent-Insensitive Search

```sql
-- Accent-insensitive matching
CREATE TABLE cities (
  id INT,
  name STRING COLLATE UNICODE_CI_AI
);

INSERT INTO cities VALUES (1, 'Montreal'), (2, 'Montreal');

SELECT * FROM cities WHERE name = 'Montreal';
-- Returns both: Montreal and Montreal (treats e and e as equal)
```

#### Locale-Aware Sorting

```sql
-- German sorting (umlauts sort correctly)
SELECT name
FROM german_customers
ORDER BY name COLLATE DE;
-- Sorts: Arzte before Bauer (A treated as A+e in German sorting)

-- Swedish sorting (A, A, O sort after Z)
SELECT name
FROM swedish_customers
ORDER BY name COLLATE SV;
```

#### Trailing Space Handling

```sql
-- RTRIM modifier ignores trailing spaces
SELECT 'Hello' COLLATE UTF8_BINARY_RTRIM = 'Hello   ';
-- Returns: true

SELECT 'Hello' COLLATE UTF8_BINARY = 'Hello   ';
-- Returns: false
```

#### Catalog-Wide Case-Insensitive Setup

```sql
-- Create a catalog where everything is case-insensitive by default
CREATE CATALOG app_data DEFAULT COLLATION UNICODE_CI;

USE CATALOG app_data;
CREATE SCHEMA users_schema;
USE SCHEMA users_schema;

-- All STRING columns automatically use UNICODE_CI
CREATE TABLE accounts (
  id INT,
  username STRING,  -- UNICODE_CI inherited from catalog
  email STRING       -- UNICODE_CI inherited from catalog
);

-- Queries are automatically case-insensitive
SELECT * FROM accounts WHERE username = 'admin';
-- Matches: Admin, ADMIN, admin, aDmIn, etc.
```

### Limitations and Notes

- `CHECK` constraints and generated column expressions require `UTF8_BINARY` default collation.
- `hive_metastore` catalog tables do not support collation constraints.
- `ALTER SCHEMA ... DEFAULT COLLATION` only affects newly created objects, not existing ones.
- Mixing two different explicit collations in the same expression raises an error.
- `UTF8_LCASE` is used internally for Databricks identifier resolution (catalog, schema, table, column names).
- Databricks normalizes collation names by removing defaults (e.g., `SR_CYR_SRN_CS_AS` simplifies to `SR`).
- Collation modifiers require Databricks Runtime 16.2+.
- Catalog/Schema-level `DEFAULT COLLATION` requires Databricks Runtime 17.1+.
