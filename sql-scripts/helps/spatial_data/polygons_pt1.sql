-- =====================================================
-- Example 1: Create a LINESTRING geometry (open path)
-- =====================================================
DECLARE @Sq GEOMETRY = 
    GEOMETRY::STGeomFromText('LINESTRING (10 10, 10 100, 100 100, 100 10, 10 10)', 0);

SELECT @Sq AS LineStringExample;
-- LINESTRING: sequence of points connected by straight lines

-- =====================================================
-- Example 2: Create a CIRCULARSTRING geometry (curved line)
-- =====================================================
DECLARE @circle GEOMETRY = 
    GEOMETRY::Parse('CIRCULARSTRING(3 2, 2 3, 1 2, 2 1, 3 2)');

SELECT @circle AS CircularStringExample;
-- CIRCULARSTRING: sequence of points forming smooth circular arcs

-- =====================================================
-- Example 3: Create a TRIANGLE polygon
-- =====================================================
DECLARE @Tri GEOMETRY = 
    GEOMETRY::STGeomFromText('POLYGON((100 100, 200 300, 300 100, 100 100))', 0);

SELECT @Tri AS TrianglePolygon;
-- POLYGON: closed shape defined by outer ring of points

-- =====================================================
-- Example 4: Create a filled SQUARE polygon
-- =====================================================
DECLARE @Sqfilled GEOMETRY = 
    GEOMETRY::STGeomFromText('POLYGON((10 10, 10 100, 100 100, 100 10, 10 10))', 0);

SELECT @Sqfilled AS SquarePolygon;
-- POLYGON: closed shape representing an area

-- =====================================================
-- Example 5: Persisted geography point column definition
-- =====================================================
-- [position] AS ([geography]::Point([latitude],[longitude],4326)) PERSISTED NOT NULL
-- Creates a persisted computed column storing a single point in WGS84 (SRID 4326)

-- =====================================================
-- Example 6: Combine multiple geometries using UNION ALL
-- =====================================================
DECLARE @Sq2 GEOMETRY = 
    GEOMETRY::STGeomFromText('POLYGON((15 15, 15 250, 250 250, 250 15, 15 15))', 0),
    @Tri2 GEOMETRY = 
    GEOMETRY::STGeomFromText('POLYGON((100 100, 200 300, 300 100, 100 100))', 0);

-- Return both geometries in one result set
SELECT @Sq2 AS GeometryExample
UNION ALL
SELECT @Tri2 AS GeometryExample;