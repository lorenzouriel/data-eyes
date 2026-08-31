-- Force a plan for a query (apply forcing policy)
-- SQL Server tries to force the plan in the optimizer. If plan forcing fails, an Extended Event is fired and the optimizer is instructed to optimize in the normal way.

EXEC sp_query_store_force_plan @query_id = 48, @plan_id = 49;

-- When you use sp_query_store_force_plan, you can only force plans recorded by Query Store as a plan for that query. 
-- In other words, the only plans available for a query are plans that were already used to execute that query while Query Store was active.

-- Remove plan forcing for a query
-- To rely again on the SQL Server query optimizer to calculate the optimal query plan, use sp_query_store_unforce_plan to unforce the plan that was selected for the query.

EXEC sp_query_store_unforce_plan @query_id = 48, @plan_id = 49;