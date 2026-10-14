-- =============================================
-- FUNCTION: dbo.google_data
-- PURPOSE: Call Google Maps API to retrieve geolocation (latitude, longitude)
--          and address details for a given input address.
-- PARAMETERS:
--   @address VARCHAR(1000) - The address to search
--   @limit INT = 1          - Number of results to return (default 1)
-- RETURNS: Table with columns
--   latitude FLOAT
--   longitude FLOAT
--   address NVARCHAR(1000)
-- NOTES:
-- - Uses sp_OACreate / sp_OAMethod for HTTP requests (requires Ole Automation Procedures enabled)
-- - Parses JSON response using OPENJSON
-- - Collation applied to handle special characters in addresses
-- =============================================
CREATE FUNCTION [dbo].[google_data](
    @address VARCHAR(1000),
    @limit INT = 1
)
RETURNS @table TABLE(
    latitude FLOAT,
    longitude FLOAT,
    address NVARCHAR(1000)
)
WITH EXECUTE AS OWNER
AS
BEGIN
    -- Declare variables
    DECLARE @url NVARCHAR(MAX);
    DECLARE @Object INT;
    DECLARE @ResponseText NVARCHAR(MAX);

    -- Build Google Maps API URL
    SET @url = CONCAT(
        'http://google.com.br/?format=json&addressdetails=0&q=',
        @address COLLATE SQL_Latin1_General_CP1253_CI_AI,
        '&format=json&limit=',
        CAST(@limit AS VARCHAR(2))
    );

    -- Create XMLHTTP object for HTTP request
    EXEC sp_OACreate 'MSXML2.XMLHTTP', @Object OUT;

    -- Open HTTP GET request
    EXEC sp_OAMethod @Object, 'open', NULL, 'GET', @url, 'false';

    -- Send HTTP request
    EXEC sp_OAMethod @Object, 'send';

    -- Get response text
    EXEC sp_OAMethod @Object, 'responseText', @ResponseText OUTPUT;

    -- Destroy the COM object
    EXEC sp_OADestroy @Object;

    -- Parse JSON response and insert into return table
    INSERT INTO @table (latitude, longitude, address)
    SELECT
        latitude,
        longitude,
        display_name
    FROM OPENJSON(@ResponseText)
    WITH (
        latitude FLOAT '$.lat',
        longitude FLOAT '$.lon',
        display_name NVARCHAR(MAX) '$.display_name',
        road NVARCHAR(MAX) '$.address.road',
        neighbourhood NVARCHAR(MAX) '$.address.neighbourhood',
        suburb NVARCHAR(MAX) '$.address.suburb',
        city NVARCHAR(MAX) '$.address.city',
        state NVARCHAR(MAX) '$.address.state',
        postcode NVARCHAR(MAX) '$.address.postcode',
        country NVARCHAR(MAX) '$.address.country'
    );

    RETURN;
END;
GO