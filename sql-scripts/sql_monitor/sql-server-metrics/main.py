import pymssql
import time
from opentelemetry.metrics import Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.metrics import get_meter_provider, set_meter_provider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

# Configuração do Exportador OTLP
otlp_exporter = OTLPMetricExporter(endpoint="http://localhost:4317", insecure=True)
reader = PeriodicExportingMetricReader(otlp_exporter)
provider = MeterProvider(metric_readers=[reader])
set_meter_provider(provider)
meter = get_meter_provider().get_meter("sqlserver_metrics")

# Conexão com SQL Server
conn = pymssql.connect(
    server=".",
    user="-",
    password="-",
    database="master"
)
cursor = conn.cursor()
print('Conexão com o SQL Server estabelecida')

# Funções para Coletar Métricas
def get_availability(callback_options):
    try:
        cursor.execute("SELECT 1")
        return [Observation(100)]  # Disponível
    except:
        return [Observation(0)]  # Indisponível

def get_active_connections(callback_options):
    cursor.execute("SELECT COUNT(*) FROM sys.dm_exec_sessions WHERE status = 'running'")
    return [Observation(cursor.fetchone()[0])]

def get_idle_connections(callback_options):
    cursor.execute("SELECT COUNT(*) FROM sys.dm_exec_sessions WHERE status = 'sleeping'")
    return [Observation(cursor.fetchone()[0])]

def get_last_backup_time(callback_options):
    cursor.execute("SELECT MAX(backup_finish_date) FROM msdb.dbo.backupset")
    last_backup = cursor.fetchone()[0]
    return [Observation(int(last_backup.timestamp()))] if last_backup else [Observation(0)]

# Definição das métricas observáveis
db_availability = meter.create_observable_gauge(
    name="sqlserver_availability",
    description="Percentual de tempo de disponibilidade do banco",
    unit="%",
    callbacks=[get_availability],
)

active_connections = meter.create_observable_gauge(
    name="sqlserver_active_connections",
    description="Número de conexões ativas no banco",
    unit="connections",
    callbacks=[get_active_connections],
)

idle_connections = meter.create_observable_gauge(
    name="sqlserver_idle_connections",
    description="Número de conexões ociosas",
    unit="connections",
    callbacks=[get_idle_connections],
)

last_backup_time = meter.create_observable_gauge(
    name="sqlserver_last_backup_time",
    description="Último backup realizado (timestamp)",
    unit="seconds",
    callbacks=[get_last_backup_time],
)

# Definição das métricas não observáveis
query_exec_time = meter.create_histogram(
    name="sqlserver_query_execution_time",
    description="Tempo médio de execução das consultas",
    unit="ms",
)

slow_queries = meter.create_counter(
    name="sqlserver_slow_queries",
    description="Número de consultas que excederam 30s",
)

def get_query_execution_time():
    cursor.execute("""
        SELECT TOP 10 total_elapsed_time / execution_count AS avg_time
        FROM sys.dm_exec_query_stats
        ORDER BY avg_time DESC
    """)
    rows = cursor.fetchall()
    for row in rows:
        query_exec_time.record(row[0])

def get_slow_queries():
    cursor.execute("""
        SELECT COUNT(*) FROM sys.dm_exec_requests
        WHERE total_elapsed_time > 30000  -- 30 segundos
    """)
    slow_queries.add(cursor.fetchone()[0])

# Loop para atualização periódica das métricas
while True:
    get_query_execution_time()
    get_slow_queries()
    time.sleep(10)
