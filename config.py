from pathlib import Path

PROJECT_NAME = "goodstudy"
SITE_NAME = "좋은공부"
SITE_NAME_EN = "GoodStudy"
SITE_URL = "https://goodstudy.co.kr"
CANONICAL_HOST = "goodstudy.co.kr"
TRAILING_SLASH = True

ROOT_DIR = Path(__file__).resolve().parent
SOURCE_EXCEL = ROOT_DIR / "data" / "주요지역과 학교 분몬.xlsx"
OUTPUT_DIR = ROOT_DIR / "output"
CANDIDATE_OUTPUT_DIR = ROOT_DIR / "candidate_output"
INTERMEDIATE_DIR = ROOT_DIR / "intermediate"
AUDIT_DIR = ROOT_DIR / "audit"
TEMPLATE_DIR = ROOT_DIR / "templates"
ASSET_DIR = ROOT_DIR / "assets"
