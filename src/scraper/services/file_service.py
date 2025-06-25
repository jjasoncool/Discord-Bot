"""
檔案處理服務
負責 JSON 檔案的讀寫操作
"""
import os
import json
from datetime import datetime
from typing import Any, Dict, List
from utils.logger import get_logger


class FileService:
    """檔案處理服務類別"""

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.logger = get_logger('file_service')
        self._ensure_directory()

    def _ensure_directory(self):
        """確保輸出目錄存在"""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            self.logger.info(f"建立目錄: {self.output_dir}")

    def save_json(self, data: Any, filename: str) -> bool:
        """
        儲存資料為 JSON 檔案

        Args:
            data: 要儲存的資料
            filename: 檔案名稱

        Returns:
            成功與否
        """
        try:
            file_path = os.path.join(self.output_dir, filename)

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.logger.info(f"成功儲存檔案: {file_path}")
            return True

        except Exception as e:
            self.logger.error(f"儲存檔案失敗 ({filename}): {str(e)}")
            return False

    def load_json(self, filename: str) -> Any:
        """
        載入 JSON 檔案

        Args:
            filename: 檔案名稱

        Returns:
            檔案內容或 None
        """
        try:
            file_path = os.path.join(self.output_dir, filename)

            if not os.path.exists(file_path):
                return None

            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        except Exception as e:
            self.logger.error(f"載入檔案失敗 ({filename}): {str(e)}")
            return None

    def load_json_with_filter(self, filename: str, filter_ids: List[int] = None, id_field: str = "articleId") -> List[Dict]:
        """
        載入 JSON 檔案並過濾指定 ID

        Args:
            filename: 檔案名稱
            filter_ids: 要過濾的 ID 列表，None 表示載入全部
            id_field: ID 欄位名稱（預設為 articleId）

        Returns:
            過濾後的資料列表
        """
        try:
            file_path = os.path.join(self.output_dir, filename)

            if not os.path.exists(file_path):
                return []

            # 使用串流方式讀取，避免一次載入整個檔案
            filtered_data = []

            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

                # 如果是列表，進行過濾
                if isinstance(data, list):
                    if filter_ids is None:
                        return data

                    # 轉換為 set 提升查找效能
                    filter_set = set(filter_ids)

                    for item in data:
                        if isinstance(item, dict) and item.get(id_field) in filter_set:
                            filtered_data.append(item)

                    self.logger.info(f"從 {len(data)} 筆資料中過濾出 {len(filtered_data)} 筆")
                    return filtered_data
                else:
                    # 如果不是列表，直接返回
                    return data if filter_ids is None else []

        except Exception as e:
            self.logger.error(f"過濾載入檔案失敗 ({filename}): {str(e)}")
            return []

    def get_article_ids_from_json(self, filename: str, id_field: str = "articleId") -> List[int]:
        """
        快速取得 JSON 檔案中的所有文章 ID

        Args:
            filename: 檔案名稱
            id_field: ID 欄位名稱

        Returns:
            ID 列表
        """
        try:
            file_path = os.path.join(self.output_dir, filename)

            if not os.path.exists(file_path):
                return []

            ids = []
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and id_field in item:
                            ids.append(item[id_field])

            return ids

        except Exception as e:
            self.logger.error(f"取得 ID 列表失敗 ({filename}): {str(e)}")
            return []

    def append_to_json(self, new_data: List[Dict], filename: str, id_field: str = "articleId") -> bool:
        """
        將新資料追加到 JSON 檔案，避免重複

        Args:
            new_data: 要追加的新資料
            filename: 檔案名稱
            id_field: ID 欄位名稱，用於去重

        Returns:
            成功與否
        """
        try:
            file_path = os.path.join(self.output_dir, filename)

            # 載入現有資料
            existing_data = self.load_json(filename) or []

            if not isinstance(existing_data, list):
                existing_data = []

            # 建立現有 ID 的 set 用於快速查找
            existing_ids = {item.get(id_field) for item in existing_data if isinstance(item, dict)}

            # 過濾新資料，只保留不重複的
            unique_new_data = []
            for item in new_data:
                if isinstance(item, dict) and item.get(id_field) not in existing_ids:
                    unique_new_data.append(item)

            if unique_new_data:
                # 合併資料
                combined_data = existing_data + unique_new_data

                # 儲存合併後的資料
                success = self.save_json(combined_data, filename)
                if success:
                    self.logger.info(f"追加 {len(unique_new_data)} 筆新資料到 {filename}")
                return success
            else:
                self.logger.debug(f"沒有新資料需要追加到 {filename}")
                return True

        except Exception as e:
            self.logger.error(f"追加資料失敗 ({filename}): {str(e)}")
            return False

    def get_file_size_mb(self, filename: str) -> float:
        """
        取得檔案大小（MB）

        Args:
            filename: 檔案名稱

        Returns:
            檔案大小（MB）
        """
        try:
            file_path = os.path.join(self.output_dir, filename)
            if os.path.exists(file_path):
                size_bytes = os.path.getsize(file_path)
                return size_bytes / (1024 * 1024)  # 轉換為 MB
            return 0.0
        except Exception:
            return 0.0
