"""Clear stale download_entries from killed scrapes before restart."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.supabase_client import get_db_connection

c = get_db_connection(new_connection=True); cur = c.cursor()
cur.execute(
    "DELETE FROM download_entries "
    "WHERE source_table_link IN ('abastecimiento_series_historicas','insumos_series_historicas') "
    "AND processed_status = FALSE"
)
print('Cleared abast/insumos stale entries:', cur.rowcount)
c.commit(); cur.close(); c.close()
