-- =====================================================
-- Step 1: Create a point in geography type (WGS84 coordinates)
-- =====================================================
DECLARE @scb0 GEOGRAPHY = 
    GEOGRAPHY::STGeomFromText('POINT(-90.851758 44.292658)', 4326);

-- =====================================================
-- Step 2: Create a buffer around the point (50 meters)
-- =====================================================
SET @scb0 = @scb0.STBuffer(50);
-- STBuffer(distance): creates a circular polygon around a point
-- distance is in meters for geography type

-- =====================================================
-- Step 3: Convert the buffered geography to geometry type
-- =====================================================
DECLARE @scb1 GEOMETRY = GEOMETRY::STGeomFromText(@scb0.ToString(), 4326);

-- =====================================================
-- Step 4: Create the Minimum Bounding Rectangle (MBR)
-- =====================================================
SET @scb1 = @scb1.STEnvelope();
-- STEnvelope() returns the axis-aligned rectangle covering the shape

-- =====================================================
-- Step 5: Convert the MBR back to geography type
-- =====================================================
SET @scb0 = GEOGRAPHY::STGeomFromText(@scb1.ToString(), 4326);

-- =====================================================
-- Step 6: View the result
-- =====================================================
SELECT @scb0 AS BufferedAndEnvelopedPoint;

-- =====================================================
-- One-liner alternative using BufferWithTolerance
-- =====================================================
-- Point(latitude=45, longitude=-90), buffer 11,000 meters, tolerance 1,000 meters
SELECT GEOGRAPHY::Point(45, -90, 4326)
       .BufferWithTolerance(11000, 1000, 0) AS BufferedPoint;
-- BufferWithTolerance(distance, tolerance, maxPoints) 
-- allows you to control the number of vertices approximating the circle