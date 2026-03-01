from datetime import date
import datetime
import json
import requests
import os
import pandas as pd
import io
import urllib3

class FileDownloader:
    """
    A class to download a file from a URL and save its contents into a JSON file.
    """

    def __init__(self, download_dir: str = "downloads"):
        self.download_dir = download_dir
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

    def _parse_taoyuan_airport_excel(self, data: bytes):
        """
        Parses the specific Taoyuan Airport Excel layout which contains three tables side-by-side.
        """
        try:
            # Read the excel without headers first
            df = pd.read_excel(io.BytesIO(data), header=None)
            
            # Helper to extract a table from specific column range
            def extract_table(start_col, end_col):
                # Columns for this table
                table_df = df.iloc[:, start_col:end_col].copy()
                
                # Title search in the first few rows (usually row 1)
                title = "Unknown Table"
                header_row_idx = 2 # Default header row
                
                for r in range(min(5, len(df))):
                    row_vals = df.iloc[r, start_col:end_col].tolist()
                    for val in row_vals:
                        val_str = str(val)
                        if val_str and val_str != 'nan' and '預報表' in val_str:
                            title = val_str
                            # Usually the headers are in the next row or the one after
                            # But we'll look for "時間區間" to be sure
                            break
                    if title != "Unknown Table":
                        break
                
                # Find the header row (the one containing "時間區間")
                for r in range(min(10, len(df))):
                    if "時間區間" in [str(x).strip() for x in df.iloc[r, start_col:end_col].tolist()]:
                        header_row_idx = r
                        break

                # Row at header_row_idx is the actual column headers
                raw_headers = df.iloc[header_row_idx, start_col:end_col].tolist()
                headers = []
                for i, h in enumerate(raw_headers):
                    h_str = str(h).strip()
                    if not h_str or h_str == 'nan':
                        headers.append(f"column_{i}")
                    else:
                        # Ensure uniqueness
                        if h_str in headers:
                            headers.append(f"{h_str}_{i}")
                        else:
                            headers.append(h_str)

                # Data starts from row header_row_idx + 1
                data_rows = table_df.iloc[header_row_idx+1:].copy()
                data_rows.columns = headers
                
                # Drop rows where the first column (usually '時間區間') is NaN
                data_rows = data_rows.dropna(subset=[headers[0]], how='all')
                
                # Convert numeric columns to appropriate types
                for col in data_rows.columns:
                    try:
                        # First attempt to convert to numeric
                        data_rows[col] = pd.to_numeric(data_rows[col], errors='ignore')
                        
                        # If the column is now numeric, check if it can be represented as integers
                        if pd.api.types.is_float_dtype(data_rows[col]):
                            non_nan = data_rows[col].dropna()
                            if not non_nan.empty and (non_nan == non_nan.astype(int)).all():
                                data_rows[col] = data_rows[col].astype('Int64')
                    except:
                        pass

                def sanitize_value(v):
                    if pd.isna(v):
                        return 0
                    if isinstance(v, (pd.Int64Dtype, int, float)):
                        try:
                            if float(v).is_integer():
                                return int(v)
                        except:
                            pass
                    return v

                records = [
                    {k: sanitize_value(v) for k, v in record.items()}
                    for record in data_rows.to_dict(orient='records')
                ]

                return {
                    "title": title,
                    "records": records
                }

            # Find all columns that contain '預報表' in any of the first few rows
            title_cols = []
            for c in range(df.shape[1]):
                for r in range(min(5, len(df))):
                    val = str(df.iloc[r, c])
                    if '預報表' in val:
                        title_cols.append((c, val))
                        break
            
            tables = {}
            if not title_cols:
                # Fallback to fixed mapping if no titles found (though this shouldn't happen)
                tables = {
                    "total": extract_table(0, 9),
                    "terminal_1": extract_table(10, 16),
                    "terminal_2": extract_table(17, 23)
                }
            else:
                for i, (start_col, title) in enumerate(title_cols):
                    # End col is either the next start_col or the end of the sheet
                    # We subtract 1 if the next col is empty, but the extract_table handles it
                    end_col = title_cols[i+1][0] if i+1 < len(title_cols) else df.shape[1]
                    
                    key = None
                    if "總計" in title: key = "total"
                    elif "第一航廈" in title: key = "terminal_1"
                    elif "第二航廈" in title: key = "terminal_2"
                    
                    if key:
                        tables[key] = extract_table(start_col, end_col)
            
            return tables
        except Exception as e:
            print(f"Failed to parse Taoyuan Airport Excel: {e}")
            import traceback
            traceback.print_exc()
            return {"raw_error": str(e)}

    def download_and_store_as_json(self, url: str, filename: str, verify: bool = True):
        """
        Downloads data from a URL and stores it as a JSON file.
        If it's an Excel file from Taoyuan Airport, transforms it using specific logic.
        """
        try:
            if not verify:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            response = requests.get(url, timeout=10, verify=verify)
            response.raise_for_status()
            data = response.content
            
            # Check if it's an Excel file (XLS or XLSX)
            if url.lower().endswith(('.xls', '.xlsx')) and "taoyuan-airport.com" in url:
                json_data_content = self._parse_taoyuan_airport_excel(data)
            elif url.lower().endswith(('.xls', '.xlsx')):
                try:
                    df = pd.read_excel(io.BytesIO(data))
                    json_data_content = df.to_dict(orient='records')
                except Exception as e:
                    print(f"Pandas failed to read excel: {e}")
                    try:
                        json_data_content = json.loads(data.decode('utf-8'))
                    except (ValueError, UnicodeDecodeError):
                        json_data_content = {"raw_content": data.decode('utf-8', errors='ignore')}
            else:
                try:
                    json_data_content = json.loads(data.decode('utf-8'))
                except (ValueError, UnicodeDecodeError):
                    json_data_content = {"raw_content": data.decode('utf-8', errors='ignore')}

            final_json_data = {
                "url": url,
                "data": json_data_content
            }

            file_path = os.path.join(self.download_dir, filename)
            if not file_path.endswith('.json'):
                file_path += '.json'

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(final_json_data, f, ensure_ascii=False, indent=4)
            
            return file_path
        except Exception as e:
            print(f"Error downloading {url}: {e}")
            return None

class MetarDownloader:
    """
    A class to fetch METAR and TAF data for a specific station.
    """
    def __init__(self):
        self.base_url = "https://aviationweather.gov/api/data/metar"

    def fetch_metar_taf(self, station_id: str = "RCTP"):
        """
        Fetches METAR and TAF for the given station ID.
        Returns a tuple of (metar, taf) or (None, None) on error.
        """
        url = f"{self.base_url}?ids={station_id}&taf=1&format=json"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not data or not isinstance(data, list):
                return None, None
            
            station_data = data[0]
            metar = station_data.get('rawOb')
            taf = station_data.get('rawTaf')
            return metar, taf
        except Exception as e:
            print(f"Error fetching METAR for {station_id}: {e}")
            return None, None

if __name__ == "__main__":
    # Example usage
    date_str = datetime.datetime.now().strftime("%Y_%m_%d")
    filename = f"{date_str}_update.json"
    url = f"https://www.taoyuan-airport.com/uploads/fos/{date_str}_update.xls"

    downloader = FileDownloader()
    _ = downloader.download_and_store_as_json(url, filename, verify=False)
    metar_downloader = MetarDownloader()
    m, t = metar_downloader.fetch_metar_taf("RCTP")
    if m:
        print(f"METAR: {m}")
        print(f"TAF: {t}")
