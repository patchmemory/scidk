import csv
from pathlib import Path


class CsvInterpreter:
    id = "csv"
    name = "CSV Interpreter"
    version = "0.1.0"
    extensions = [".csv"]

    def __init__(self, max_bytes: int = 10 * 1024 * 1024):
        self.max_bytes = max_bytes

    def interpret(self, file_path: Path):
        try:
            size = file_path.stat().st_size
            if size > self.max_bytes:
                return {
                    'status': 'error',
                    'data': {
                        'error_type': 'FILE_TOO_LARGE',
                        'max_bytes': self.max_bytes,
                        'size_bytes': size,
                        'details': f"CSV file exceeds limit of {self.max_bytes} bytes"
                    }
                }
            # Try to detect dialect
            with open(file_path, 'r', encoding='utf-8', errors='ignore', newline='') as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=[',', '\t', ';', '|'])
                except Exception:
                    dialect = csv.get_dialect('excel')
                reader = csv.reader(f, dialect)
                headers = []
                row_count = 0
                sample_rows = []
                # Read first non-empty row as headers
                for row in reader:
                    if any(cell.strip() for cell in row):
                        headers = [cell.strip() for cell in row]
                        break
                # Count remaining rows and capture a small sample
                max_sample = 5
                for row in reader:
                    if not any(cell.strip() for cell in row):
                        continue
                    row_count += 1
                    if len(sample_rows) < max_sample:
                        sample_rows.append(row)
                delimiter = getattr(dialect, 'delimiter', ',')
                return {
                    'status': 'success',
                    'data': {
                        'type': 'csv',
                        'delimiter': delimiter,
                        'headers': headers,
                        'row_count': row_count,
                        'sample_rows': sample_rows,
                    }
                }
        except Exception as e:
            return {
                'status': 'error',
                'data': {
                    'error_type': 'CSV_INTERPRET_ERROR',
                    'details': str(e),
                }
            }
