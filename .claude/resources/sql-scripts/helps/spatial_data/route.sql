-- ================================================
-- Drop the points table if it exists
-- ================================================
DROP TABLE IF EXISTS [points];
GO

-- ================================================
-- Create table to store GPS points
-- geog: geography type
-- Geom: computed geometry type from geography
-- ================================================
CREATE TABLE [points]
(
    [Id] INT IDENTITY, 
    [geog] GEOGRAPHY,
    [Geom] AS GEOMETRY::STGeomFromWKB(geog.STAsBinary(), geog.STSrid)
);
GO

-- ================================================
-- Insert GPS points for a specific asset and track
-- ================================================
DECLARE
    @id INT = 269559161,         -- Track ID
    @asset_id INT = 40379;       -- Asset ID

INSERT INTO points (geog)  
SELECT 
	[position]
FROM [datas]
WHERE [asset_id] = @asset_id
  AND [utc_timestamp] BETWEEN 
        (SELECT CAST(DATEADD(hour, 3, [start_timestamp]) AS DATETIME) 
         FROM [tracking] 
         WHERE [id] = @id)
    AND (SELECT CAST(DATEADD(hour, 3, [end_timestamp]) AS DATETIME) 
         FROM [tracking] 
         WHERE [id] = @id)
ORDER BY [utc_timestamp] ASC;
GO

-- ================================================
-- Check the inserted points
-- ================================================
SELECT * FROM [points];
GO

-- ================================================
-- Build a LINESTRING geometry from the points
-- ================================================
DECLARE
    @iterRow INT,
    @rowCount INT,
    @string VARCHAR(MAX),
    @x VARCHAR(20),
    @y VARCHAR(20),
    @route GEOMETRY;

-- Initialize variables
SELECT 
    @iterRow = 1,
    @rowCount = COUNT(1)
FROM points;

-- Concatenate points into a LINESTRING
WHILE (@iterRow <= @rowCount)
BEGIN   
    SELECT  
        @x = CAST(Geom.STX AS VARCHAR(20)),
        @y = CAST(Geom.STY AS VARCHAR(20))
    FROM points
    WHERE Id = @iterRow;

    SET @string = ISNULL(@string + ',', '') + @x + ' ' + @y;
    SET @iterRow += 1;
END

SET @string = 'LINESTRING(' + @string + ')';   
SET @route = GEOMETRY::STLineFromText(@string, 0);

-- ================================================
-- Save the route geometry to the [routes] table
-- ================================================
UPDATE [routes]
SET [route] = @route
WHERE [id] = 264202407;
GO

-- ================================================
-- Calculate total distance of the route
-- ================================================
SELECT [distance] = @route.STLength();
GO

-- Optional: drop the temporary points table if no longer needed
-- DROP TABLE [points];