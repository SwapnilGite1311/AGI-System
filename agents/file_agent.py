"""
File Agent - File system operations and organization
Handles all file/folder operations intelligently
"""

import os
import shutil
import json
import hashlib
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
from loguru import logger


class FileAgent:
    """
    Handles all file system operations:
    - File/folder creation, deletion, moving
    - Automatic organization with undo support
    - Search and filtering
    - Backup operations
    - Duplicate detection & disk analysis
    """
    
    def __init__(self, config_path: str = "./config/settings.json"):
        """Initialize file agent"""
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.home = Path.home()
        
        # Load file_agent config
        fa_config = self.config.get("file_agent", {})
        self.undo_manifest_dir = Path(fa_config.get("undo_manifest_dir", "./data/undo_manifests"))
        self.undo_manifest_dir.mkdir(parents=True, exist_ok=True)
        self.max_undo_manifests = int(fa_config.get("max_undo_manifests", 20))
        self.hash_algo = fa_config.get("duplicate_hash_algorithm", "md5")
        self.max_files_for_hash = int(fa_config.get("max_files_for_hash", 5000))
        
        logger.info("📁 File Agent initialized (enhanced)")
    
    # ============= BASIC FILE OPERATIONS =============
    
    def create_file(self, filepath: str, content: str = "") -> Dict[str, Any]:
        """
        Create a new file
        
        Args:
            filepath: Path to file
            content: Initial content
        
        Returns:
            Result with file info
        """
        
        try:
            path = Path(filepath)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
            
            logger.success("✅ Created file: {}", filepath)
            return {
                "success": True,
                "path": str(path),
                "size": path.stat().st_size
            }
            
        except Exception as e:
            logger.error("❌ Create file failed: {}", str(e))
            return {"success": False, "error": str(e)}
    
    def create_folder(self, folderpath: str) -> Dict[str, Any]:
        """Create a new folder"""
        
        try:
            path = Path(folderpath)
            path.mkdir(parents=True, exist_ok=True)
            
            logger.success("✅ Created folder: {}", folderpath)
            return {"success": True, "path": str(path)}
            
        except Exception as e:
            logger.error("❌ Create folder failed: {}", str(e))
            return {"success": False, "error": str(e)}
    
    def delete_file(self, filepath: str) -> Dict[str, Any]:
        """Delete a file"""
        
        try:
            path = Path(filepath)
            if path.is_file():
                path.unlink()
                logger.info("🗑️ Deleted file: {}", filepath)
                return {"success": True, "path": str(path)}
            else:
                return {"success": False, "error": "Not a file"}
                
        except Exception as e:
            logger.error("❌ Delete file failed: {}", str(e))
            return {"success": False, "error": str(e)}
    
    def delete_folder(self, folderpath: str, recursive: bool = False) -> Dict[str, Any]:
        """
        Delete a folder
        
        Args:
            folderpath: Path to folder
            recursive: If True, delete even if not empty
        """
        
        try:
            path = Path(folderpath)
            if path.is_dir():
                if recursive:
                    shutil.rmtree(path)
                else:
                    path.rmdir()  # Only works if empty
                
                logger.info("🗑️ Deleted folder: {}", folderpath)
                return {"success": True, "path": str(path)}
            else:
                return {"success": False, "error": "Not a folder"}
                
        except Exception as e:
            logger.error("❌ Delete folder failed: {}", str(e))
            return {"success": False, "error": str(e)}
    
    def move_file(self, source: str, destination: str) -> Dict[str, Any]:
        """Move/rename a file"""
        
        try:
            src = Path(source)
            dst = Path(destination)
            
            # Create destination folder if needed
            dst.parent.mkdir(parents=True, exist_ok=True)
            
            shutil.move(str(src), str(dst))
            
            logger.info("📦 Moved: {} -> {}", source, destination)
            return {
                "success": True,
                "source": str(src),
                "destination": str(dst)
            }
            
        except Exception as e:
            logger.error("❌ Move file failed: {}", str(e))
            return {"success": False, "error": str(e)}
    
    def copy_file(self, source: str, destination: str) -> Dict[str, Any]:
        """Copy a file"""
        
        try:
            src = Path(source)
            dst = Path(destination)
            
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            
            logger.info("📋 Copied: {} -> {}", source, destination)
            return {
                "success": True,
                "source": str(src),
                "destination": str(dst)
            }
            
        except Exception as e:
            logger.error("❌ Copy file failed: {}", str(e))
            return {"success": False, "error": str(e)}
    
    # ============= FILE INFORMATION =============
    
    def get_file_info(self, filepath: str) -> Dict[str, Any]:
        """Get detailed file information"""
        
        try:
            path = Path(filepath)
            stat = path.stat()
            
            return {
                "success": True,
                "name": path.name,
                "path": str(path.absolute()),
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / (1024*1024), 2),
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "extension": path.suffix,
                "is_file": path.is_file(),
                "is_folder": path.is_dir()
            }
            
        except Exception as e:
            logger.error("❌ Get file info failed: {}", str(e))
            return {"success": False, "error": str(e)}
    
    def list_files(self, folderpath: str, pattern: str = "*") -> List[Dict[str, Any]]:
        """
        List files in a folder
        
        Args:
            folderpath: Folder to list
            pattern: File pattern (e.g., "*.txt", "*.py")
        
        Returns:
            List of file information
        """
        
        try:
            path = Path(folderpath)
            files = []
            
            for item in path.glob(pattern):
                try:
                    stat = item.stat()
                    files.append({
                        "name": item.name,
                        "path": str(item),
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "is_file": item.is_file(),
                        "is_folder": item.is_dir()
                    })
                except:
                    continue
            
            logger.debug("📋 Listed {} items in {}", len(files), folderpath)
            return files
            
        except Exception as e:
            logger.error("❌ List files failed: {}", str(e))
            return []
    
    # ============= INTELLIGENT ORGANIZATION =============
    
    def organize_folder(self, folderpath: str) -> Dict[str, Any]:
        """
        Automatically organize a folder by file type.
        Creates subfolders: Documents, Images, Videos, Audio, Archives, Code, Executables, Others.
        Saves a manifest file in self.undo_manifest_dir so the action can be undone.
        """
        
        logger.info("🗂️ Organizing folder with undo tracking: {}", folderpath)
        
        # Category definitions
        categories = {
            "Documents": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx", ".ppt", ".pptx", ".md", ".csv"],
            "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".ico", ".webp"],
            "Videos": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"],
            "Audio": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"],
            "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
            "Code": [".py", ".js", ".html", ".css", ".java", ".cpp", ".c", ".json", ".xml", ".ts", ".go", ".rs"],
            "Executables": [".exe", ".msi", ".bat", ".sh", ".cmd"],
        }
        
        try:
            path = Path(folderpath)
            if not path.is_dir():
                return {"success": False, "error": f"Not a directory: {folderpath}"}
                
            moved_files = []
            moved_count = 0
            
            # Get all files (not folders)
            files = [f for f in path.iterdir() if f.is_file()]
            
            for file in files:
                # Determine category
                category = "Others"
                for cat, extensions in categories.items():
                    if file.suffix.lower() in extensions:
                        category = cat
                        break
                
                # Create category folder
                category_folder = path / category
                category_folder.mkdir(exist_ok=True)
                
                # Move file
                destination = category_folder / file.name
                
                # Handle name conflicts
                counter = 1
                while destination.exists():
                    stem = file.stem
                    destination = category_folder / f"{stem}_{counter}{file.suffix}"
                    counter += 1
                
                orig_str = str(file.absolute())
                dest_str = str(destination.absolute())
                
                shutil.move(str(file), str(destination))
                moved_files.append({"from": orig_str, "to": dest_str})
                moved_count += 1
            
            # Save manifest if any files were moved
            manifest_id = None
            if moved_count > 0:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                manifest_id = f"manifest_{timestamp}"
                manifest_path = self.undo_manifest_dir / f"{manifest_id}.json"
                
                manifest_data = {
                    "manifest_id": manifest_id,
                    "folderpath": str(path.absolute()),
                    "timestamp": datetime.now().isoformat(),
                    "moved_files": moved_files
                }
                
                manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
                self._prune_manifests()
            
            logger.success("✅ Organized {} files. Manifest ID: {}", moved_count, manifest_id)
            return {
                "success": True,
                "files_organized": moved_count,
                "categories": list(categories.keys()) + ["Others"],
                "manifest_id": manifest_id
            }
            
        except Exception as e:
            logger.error("❌ Organization failed: {}", str(e))
            return {"success": False, "error": str(e)}

    def restore_organization(self, manifest_id: str = None) -> Dict[str, Any]:
        """
        Undo a folder organization by moving files back to their original paths.
        If no manifest_id is provided, undoes the most recent one.
        """
        try:
            if not manifest_id:
                # Find most recent manifest
                manifests = sorted(self.undo_manifest_dir.glob("*.json"), key=os.path.getmtime)
                if not manifests:
                    return {"success": False, "error": "No organization history found to undo."}
                manifest_path = manifests[-1]
                manifest_id = manifest_path.stem
            else:
                manifest_path = self.undo_manifest_dir / f"{manifest_id}.json"
                if not manifest_path.exists():
                    return {"success": False, "error": f"Manifest not found: {manifest_id}"}
            
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            moved_files = manifest_data.get("moved_files", [])
            restored_count = 0
            errors = []
            
            # Iterate in reverse to avoid any conflict
            for move in reversed(moved_files):
                src = Path(move["to"])
                dst = Path(move["from"])
                
                if src.exists():
                    # Create parent folder if it was deleted
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
                    restored_count += 1
                else:
                    errors.append(f"File not found to restore: {move['to']}")
            
            # Clean up empty category folders that might have been created during organization
            folderpath = Path(manifest_data["folderpath"])
            categories = ["Documents", "Images", "Videos", "Audio", "Archives", "Code", "Executables", "Others"]
            for cat in categories:
                cat_dir = folderpath / cat
                if cat_dir.is_dir() and not any(cat_dir.iterdir()):
                    try:
                        cat_dir.rmdir()
                    except Exception:
                        pass
            
            # Delete manifest file after success
            manifest_path.unlink()
            
            return {
                "success": len(errors) == 0,
                "restored_files": restored_count,
                "errors": errors,
                "manifest_id": manifest_id
            }
            
        except Exception as e:
            logger.error("❌ Restore failed: {}", str(e))
            return {"success": False, "error": str(e)}

    def _prune_manifests(self):
        """Keep only self.max_undo_manifests manifest files."""
        try:
            manifests = sorted(self.undo_manifest_dir.glob("*.json"), key=os.path.getmtime)
            while len(manifests) > self.max_undo_manifests:
                manifests[0].unlink()
                manifests.pop(0)
        except Exception as e:
            logger.warning("Failed to prune manifests: {}", str(e))

    def find_duplicate_files(self, folderpath: str) -> Dict[str, Any]:
        """
        Find duplicate files in a folder by matching their content hashes.
        """
        logger.info("🔍 Scanning for duplicate files in: {}", folderpath)
        try:
            path = Path(folderpath)
            if not path.is_dir():
                return {"success": False, "error": f"Not a directory: {folderpath}"}
                
            files_by_size = {}
            # Group by file size first (very fast, avoids hashing everything)
            file_count = 0
            for root, _, files in os.walk(folderpath):
                for file in files:
                    file_count += 1
                    if file_count > self.max_files_for_hash:
                        logger.warning("Reached max files for hashing ({})", self.max_files_for_hash)
                        break
                    file_path = Path(root) / file
                    try:
                        if file_path.is_file() and not file_path.is_symlink():
                            size = file_path.stat().st_size
                            if size > 0: # ignore empty files
                                files_by_size.setdefault(size, []).append(file_path)
                    except Exception:
                        continue
                if file_count > self.max_files_for_hash:
                    break
            
            # For sizes with multiple files, calculate hashes
            duplicates = {}
            for size, file_list in files_by_size.items():
                if len(file_list) < 2:
                    continue
                
                hashes = {}
                for fp in file_list:
                    h = self._calculate_file_hash(fp)
                    if h:
                        hashes.setdefault(h, []).append(str(fp.absolute()))
                
                for h, paths in hashes.items():
                    if len(paths) > 1:
                        duplicates[h] = {
                            "size_bytes": size,
                            "size_mb": round(size / (1024 * 1024), 3),
                            "files": paths
                        }
            
            return {
                "success": True,
                "duplicates_found": len(duplicates),
                "duplicates": duplicates
            }
        except Exception as e:
            logger.error("❌ Duplicate detection failed: {}", str(e))
            return {"success": False, "error": str(e)}

    def _calculate_file_hash(self, file_path: Path) -> Optional[str]:
        """Helper to hash a file."""
        try:
            hasher = hashlib.new(self.hash_algo)
            # Read first 1MB or full file if smaller
            with open(file_path, "rb") as f:
                buf = f.read(1024 * 1024)
                hasher.update(buf)
            return hasher.hexdigest()
        except Exception:
            return None

    def analyze_disk_usage(self, folderpath: str) -> Dict[str, Any]:
        """
        Analyze disk space usage in a folder, returning total size and top subfolders/files.
        """
        logger.info("📊 Analyzing disk usage for: {}", folderpath)
        try:
            path = Path(folderpath)
            if not path.is_dir():
                return {"success": False, "error": f"Not a directory: {folderpath}"}
                
            total_size = 0
            items_list = []
            
            # Calculate size for direct children (subdirs and files)
            for item in path.iterdir():
                try:
                    item_size = self._get_path_size(item)
                    total_size += item_size
                    items_list.append({
                        "name": item.name,
                        "path": str(item.absolute()),
                        "is_folder": item.is_dir(),
                        "size_bytes": item_size,
                        "size_mb": round(item_size / (1024 * 1024), 2)
                    })
                except Exception:
                    continue
            
            # Sort items by size descending
            items_list.sort(key=lambda x: x["size_bytes"], reverse=True)
            
            return {
                "success": True,
                "folder_path": str(path.absolute()),
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "total_size_gb": round(total_size / (1024 * 1024 * 1024), 2),
                "items": items_list[:25] # top 25 consumers
            }
        except Exception as e:
            logger.error("❌ Disk analysis failed: {}", str(e))
            return {"success": False, "error": str(e)}

    def _get_path_size(self, path: Path) -> int:
        """Helper to get size of a file or folder recursively."""
        if path.is_file():
            return path.stat().st_size
        total = 0
        try:
            for root, _, files in os.walk(str(path)):
                for f in files:
                    fp = os.path.join(root, f)
                    if not os.path.islink(fp):
                        total += os.path.getsize(fp)
        except Exception:
            pass
        return total

    def batch_rename_files(self, folderpath: str, find_str: str, replace_str: str, extension: str = None) -> Dict[str, Any]:
        """
        Rename multiple files in a directory by replacing find_str with replace_str.
        Optionally filter by file extension (e.g. '.txt').
        """
        logger.info("✏️ Batch renaming files in: {} (replace '{}' with '{}')", folderpath, find_str, replace_str)
        try:
            path = Path(folderpath)
            if not path.is_dir():
                return {"success": False, "error": f"Not a directory: {folderpath}"}
                
            renamed = []
            errors = []
            
            for item in path.iterdir():
                if not item.is_file():
                    continue
                
                # Check extension filter
                if extension and item.suffix.lower() != extension.lower():
                    continue
                    
                if find_str in item.name:
                    new_name = item.name.replace(find_str, replace_str)
                    new_path = item.parent / new_name
                    
                    # Prevent overwriting
                    if new_path.exists():
                        errors.append(f"Cannot rename '{item.name}' to '{new_name}': Destination already exists.")
                        continue
                        
                    try:
                        item.rename(new_path)
                        renamed.append({
                            "old_name": item.name,
                            "new_name": new_name,
                            "path": str(new_path.absolute())
                        })
                    except Exception as ex:
                        errors.append(f"Failed to rename '{item.name}': {str(ex)}")
            
            return {
                "success": len(renamed) > 0,
                "renamed_count": len(renamed),
                "renamed_files": renamed,
                "errors": errors
            }
        except Exception as e:
            logger.error("❌ Batch rename failed: {}", str(e))
            return {"success": False, "error": str(e)}
    
    # ============= SEARCH =============
    
    def search_files(
        self, 
        folderpath: str, 
        query: str, 
        search_content: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search for files by name or content
        
        Args:
            folderpath: Folder to search in
            query: Search query
            search_content: If True, search inside files too
        
        Returns:
            List of matching files
        """
        
        logger.info("🔍 Searching for: {}", query)
        
        results = []
        path = Path(folderpath)
        query_lower = query.lower()
        
        try:
            # Search by filename
            for item in path.rglob("*"):
                if not item.is_file():
                    continue
                
                # Check filename
                if query_lower in item.name.lower():
                    results.append({
                        "path": str(item),
                        "name": item.name,
                        "match_type": "filename"
                    })
                
                # Check content if requested
                elif search_content and item.suffix in ['.txt', '.py', '.js', '.json', '.md']:
                    try:
                        content = item.read_text(encoding='utf-8', errors='ignore')
                        if query_lower in content.lower():
                            results.append({
                                "path": str(item),
                                "name": item.name,
                                "match_type": "content"
                            })
                    except:
                        pass
            
            logger.debug("🔍 Found {} matches", len(results))
            return results
            
        except Exception as e:
            logger.error("❌ Search failed: {}", str(e))
            return []
    
    # ============= BACKUP =============
    
    def backup_folder(self, source: str, backup_name: str = None) -> Dict[str, Any]:
        """
        Create backup of a folder
        
        Args:
            source: Folder to backup
            backup_name: Name for backup (default: auto-generated)
        """
        
        try:
            src = Path(source)
            
            if backup_name is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_name = f"{src.name}_backup_{timestamp}"
            
            # Create backups folder
            backups_dir = self.home / "AGI_Backups"
            backups_dir.mkdir(exist_ok=True)
            
            backup_path = backups_dir / backup_name
            
            # Copy entire folder
            shutil.copytree(src, backup_path)
            
            logger.success("✅ Backup created: {}", backup_path)
            return {
                "success": True,
                "source": str(src),
                "backup_path": str(backup_path)
            }
            
        except Exception as e:
            logger.error("❌ Backup failed: {}", str(e))
            return {"success": False, "error": str(e)}


# Test function
def test_file_agent():
    """Test file agent"""
    
    agent = FileAgent()
    
    # Create test folder
    test_folder = Path("./data/test_files")
    test_folder.mkdir(parents=True, exist_ok=True)
    
    print("\n=== TEST 1: Create Files ===")
    agent.create_file(str(test_folder / "test.txt"), "Hello AGI!")
    agent.create_file(str(test_folder / "document.pdf"), "")
    agent.create_file(str(test_folder / "script.py"), "print('test')")
    agent.create_file(str(test_folder / "image.png"), "")
    print("Created 4 test files")
    
    print("\n=== TEST 2: List Files ===")
    files = agent.list_files(str(test_folder))
    print(f"Found {len(files)} files:")
    for f in files:
        print(f"  - {f['name']} ({f['size']} bytes)")
    
    print("\n=== TEST 3: Get File Info ===")
    info = agent.get_file_info(str(test_folder / "test.txt"))
    print(json.dumps(info, indent=2))
    
    print("\n=== TEST 4: Organize Folder ===")
    result = agent.organize_folder(str(test_folder))
    print(f"Organized {result.get('files_organized', 0)} files")
    
    print("\n=== TEST 5: Search ===")
    results = agent.search_files(str(test_folder), "test")
    print(f"Found {len(results)} matches for 'test'")
    
    # Cleanup
    print("\n=== Cleaning up test files ===")
    shutil.rmtree(test_folder)
    print("Test complete!")


if __name__ == "__main__":
    test_file_agent()