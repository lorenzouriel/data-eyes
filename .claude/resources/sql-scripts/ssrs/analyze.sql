-- =====================================================
-- Query: ExecutionLog Analysis by Client and Report
-- Includes Author, Creation Date, and Total Reports
-- Author: Lorenzo Uriel
-- Date: 2025-08-19
-- =====================================================

SELECT 
    [Log].*,                           
    [Empresa],                          
    (SELECT COUNT([name]) FROM [reports]) AS [TotalReports] -- Total number of reports
FROM
(
    -- Inner query: counts report views by client
    SELECT
        C.[Path] AS [ReportPath],      -- Report folder path
        C.[Name] AS [ReportName],      -- Report name
        C.[CreatedBy] AS [Author],     -- Report author
        C.[CreationDate] AS [CreationDate], -- Report creation date
        -- Extract 'customer' parameter from execution log
        SUBSTRING(
            E.[Parameters],
            CHARINDEX('customer=', E.[Parameters]) + LEN('customer='),
            CHARINDEX('&', E.[Parameters] + '&', CHARINDEX('customer=', E.[Parameters])) 
                - CHARINDEX('customer=', E.[Parameters]) - LEN('customer=')
        ) AS [customer],
        COUNT(*) AS [ViewCount]        -- Number of executions for this client and report
    FROM ExecutionLog AS E
    JOIN Catalog AS C 
        ON E.ReportID = C.ItemID       -- Join to get report metadata
    WHERE E.[Parameters] LIKE '%customer=%'  -- Only logs that include a 'customer' parameter
    GROUP BY 
        C.[Path], 
        C.[Name], 
        C.[CreatedBy],
        C.[CreationDate],
        SUBSTRING(
            E.[Parameters],
            CHARINDEX('customer=', E.[Parameters]) + LEN('customer='),
            CHARINDEX('&', E.[Parameters] + '&', CHARINDEX('customer=', E.[Parameters])) 
                - CHARINDEX('customer=', E.[Parameters]) - LEN('customer=')
        )
) AS [Log]
ORDER BY [Log].[ViewCount] DESC;  -- Sort by most viewed reports per client

/************************************************************************************************
-- Retrieves all reports from the catalog along with their execution
-- parameters and counts the number of times each report was viewed.
************************************************************************************************/
SELECT
    C.[Path] AS [ReportPath],
    C.[Name] AS [ReportName],
    CAST(E.[Parameters] as varchar) AS [Parameters],
    COUNT(*) AS [ViewCount]
FROM ExecutionLog AS E
JOIN Catalog AS C ON E.ReportID = C.ItemID
GROUP BY C.Path, C.Name, CAST(E.[Parameters] as varchar)
ORDER BY ViewCount DESC

/************************************************************************************************
-- Extracts the value of the 'customer' parameter from the execution
-- logs for each report and counts the number of views per client per report.
-- Only logs containing the 'customer' parameter are considered.
************************************************************************************************/
SELECT *
FROM (
    SELECT
        C.[Path] AS [ReportPath],
        C.[Name] AS [ReportName],
        SUBSTRING(E.[Parameters],
                  CHARINDEX('customer=', E.[Parameters]) + LEN('customer='),
                  CHARINDEX('&', E.[Parameters], CHARINDEX('customer=', E.[Parameters])) 
                  - CHARINDEX('customer=', E.[Parameters]) - LEN('customer=')) AS [customer],
        COUNT(*) AS [ViewCount]
    FROM ExecutionLog AS E
    JOIN Catalog AS C ON E.ReportID = C.ItemID
    WHERE E.[Parameters] LIKE '%customer=%'
    GROUP BY C.[Path], C.[Name],
             SUBSTRING(E.[Parameters],
                       CHARINDEX('customer=', E.[Parameters]) + LEN('customer='),
                       CHARINDEX('&', E.[Parameters], CHARINDEX('customer=', E.[Parameters])) 
                       - CHARINDEX('customer=', E.[Parameters]) - LEN('customer='))
) [Log]
ORDER BY [Log].[ViewCount] DESC

/************************************************************************************************
--  Similar to Query 2, selecting reports and their 'customer' values
--   along with view counts, prepared for further extensions or additional filtering.
************************************************************************************************/
SELECT 
    [Log].*
FROM (
    SELECT
        C.[Path] AS [ReportPath],
        C.[Name] AS [ReportName],
        SUBSTRING(E.[Parameters],
                  CHARINDEX('customer=', E.[Parameters]) + LEN('customer='),
                  CHARINDEX('&', E.[Parameters], CHARINDEX('customer=', E.[Parameters])) 
                  - CHARINDEX('customer=', E.[Parameters]) - LEN('customer=')) AS [customer],
        COUNT(*) AS [ViewCount]
    FROM ExecutionLog AS E
    JOIN Catalog AS C ON E.ReportID = C.ItemID
    WHERE E.[Parameters] LIKE '%customer=%'
    GROUP BY C.[Path], C.[Name],
             SUBSTRING(E.[Parameters],
                       CHARINDEX('customer=', E.[Parameters]) + LEN('customer='),
                       CHARINDEX('&', E.[Parameters], CHARINDEX('customer=', E.[Parameters])) 
                       - CHARINDEX('customer=', E.[Parameters]) - LEN('customer='))
) [Log]
ORDER BY [Log].[ViewCount] DESC
