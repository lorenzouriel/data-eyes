-- =============================================
-- Trigger: trg_prevent_delete_where
-- Table: Employees
-- Event: INSTEAD OF DELETE
-- Purpose: Prevent deletion of all records in the Employees table
--          without a WHERE clause.
-- Author: Lorenzo Uriel
-- Date: 2025-08-19
-- =============================================

CREATE TRIGGER trg_prevent_delete_where
ON [Employees]
INSTEAD OF DELETE
AS
BEGIN
    -- =====================================================
    -- 1. Check if the deletion attempt is for all records
    -- =====================================================
    -- The 'deleted' pseudo-table contains all rows that would be deleted
    -- If the count of 'deleted' rows equals the total rows in Employees,
    -- it means someone is trying to delete everything.
    IF (SELECT COUNT(*) FROM deleted) = (SELECT COUNT(*) FROM [Employees])
    BEGIN
        -- =====================================================
        -- 2. Raise an error using RAISERROR
        -- =====================================================
        -- RAISERROR(message, severity, state)
        -- message: text displayed to the user
        -- severity: 16 = user-defined error
        -- state: arbitrary number to identify the error
        RAISERROR('You cannot delete all records! Please add a WHERE clause...', 16, 1);
        -- Stop trigger execution
        RETURN;
    END

    -- =====================================================
    -- 3. If not a full delete, allow deletion of selected records
    -- =====================================================
    DELETE E
    FROM [Employees] E
    INNER JOIN deleted D ON E.id = D.id;
END

-- Insert test data
INSERT INTO Employees (id, name) VALUES (1, 'Alice'), (2, 'Bob'), (3, 'Charlie');

-- Attempt to delete all rows (will raise RAISERROR)
DELETE FROM Employees;
-- Expected output: 
-- "You cannot delete all records! Please add a WHERE clause..."

-- Attempt to delete a specific row (will succeed)
DELETE FROM Employees WHERE id = 2;