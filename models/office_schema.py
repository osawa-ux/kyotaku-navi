"""
居宅介護支援事業所 データモデル定義

設計方針:
- OfficeMaster: 全ポータル共通コア（訪問看護 StationMaster と互換性を保つ）
- KyotakuFeatures: 居宅介護支援固有の拡張情報
- OfficeWeb: Web補完情報（Google Places等）
- ScrapeAudit: 取得監査ログ（訪問看護と完全同一）

フィールド名の汎化:
  station_id → office_id  （全ポータルで "office_id" に統一する方向）
  StationMaster → OfficeMaster

データソース:
  主: 厚労省オープンデータ jigyosho_430.csv (CC BY 4.0)
  副（将来）: 介護サービス情報公表システム、Google Places API
"""

from pydantic import BaseModel, Field
from typing import Optional


class OfficeMaster(BaseModel):
    """
    居宅介護支援事業所 基本情報（全ポータル共通コア）

    訪問看護 StationMaster との対応:
      station_id → office_id（汎化）
      それ以外のフィールドは名称・型とも互換
    """

    # --- 識別子 ---
    office_id: str = Field(description="一意識別子。形式: mhlw_kaigo:{office_code}:430")
    portal_type: str = Field(
        default="kyotaku",
        description="ポータル種別 (kyotaku / houmon_kango / zaitaku_clinic)"
    )
    service_code: str = Field(
        default="430",
        description="厚労省介護サービスコード（居宅介護支援=430）"
    )
    service_name: str = Field(
        default="居宅介護支援",
        description="サービス種別名称"
    )

    # --- 事業所基本情報 ---
    name: str = Field(description="事業所名")
    name_kana: Optional[str] = Field(default=None, description="事業所名カナ")

    # --- 所在地 ---
    prefecture: str = Field(description="都道府県（例: 北海道）")
    pref_code: str = Field(description="都道府県コード 2桁（例: '01'）")
    city: str = Field(description="市区町村（例: 札幌市中央区）")
    city_code: Optional[str] = Field(
        default=None,
        description="市区町村コード 6桁（CSV先頭カラムから取得）"
    )
    address: str = Field(description="住所（都道府県含む全文）")
    address_building: Optional[str] = Field(
        default=None,
        description="方書・ビル名等（CSV列8）"
    )
    postal_code: Optional[str] = Field(
        default=None,
        description="郵便番号 NNN-NNNN（厚労省CSVには含まれないため将来補完）"
    )

    # --- 連絡先 ---
    tel: Optional[str] = Field(default=None, description="電話番号 ハイフン付き")
    fax: Optional[str] = Field(default=None, description="FAX番号 ハイフン付き")

    # --- 法人情報 ---
    corporation_number: Optional[str] = Field(
        default=None,
        description="法人番号（13桁）。将来的な法人単位での関連付けに使用"
    )
    corporation_name: Optional[str] = Field(default=None, description="法人名称")

    # --- 事業所番号 ---
    office_code: str = Field(description="事業所番号（10桁）。厚労省CSVのNo/事業所番号カラム")

    # --- 地理情報 ---
    latitude: Optional[float] = Field(default=None, description="緯度（WGS84）")
    longitude: Optional[float] = Field(default=None, description="経度（WGS84）")

    # --- Web情報 ---
    website_url: Optional[str] = Field(default=None, description="公式サイトURL")

    # --- データソース管理 ---
    source_primary: str = Field(description="主データソース名（例: mhlw_kaigo_open_data）")
    source_url: Optional[str] = Field(default=None, description="データ取得元URL")
    source_updated_at: Optional[str] = Field(
        default=None,
        description="ソースデータ更新日（年2回: 6月末・12月末）"
    )
    retrieved_at: Optional[str] = Field(
        default=None,
        description="このレコードを取得・処理した日時 ISO8601"
    )

    # --- 状態管理 ---
    is_active: bool = Field(default=True, description="稼働中フラグ")

    # --- 生データ保持（正規化前）---
    raw_address: Optional[str] = Field(default=None, description="正規化前の住所")
    raw_name: Optional[str] = Field(default=None, description="正規化前の事業所名")
    raw_corporation_name: Optional[str] = Field(default=None, description="正規化前の法人名")


class KyotakuFeatures(BaseModel):
    """
    居宅介護支援事業所 固有の拡張情報

    厚労省CSVから取得可能な情報を格納。
    介護サービス情報公表システムから取得する詳細情報は Phase 3 で追加予定。
    """

    office_id: str = Field(description="OfficeMaster.office_id と対応")

    # --- 営業情報（CSV列16-17）---
    business_days_text: Optional[str] = Field(
        default=None,
        description="利用可能曜日（例: 平日、月〜土）"
    )
    business_days_note: Optional[str] = Field(
        default=None,
        description="利用可能曜日の特記事項"
    )

    # --- 定員（CSV列18）---
    capacity: Optional[int] = Field(
        default=None,
        description="定員（0は未記入扱い。居宅介護支援は実質上限なしのため0が多い）"
    )

    # --- 共生型・基準充足（CSV列20-22）---
    inclusive_service: Optional[bool] = Field(
        default=None,
        description="高齢者・障害者の同時一体利用（共生型サービス）対応"
    )
    meets_kaigo_standard: Optional[bool] = Field(
        default=None,
        description="介護保険の通常の指定基準を満たしている"
    )
    meets_shogai_standard: Optional[bool] = Field(
        default=None,
        description="障害福祉の通常の指定基準を満たしている"
    )

    # --- 備考（CSV列23）---
    remarks_raw: Optional[str] = Field(default=None, description="備考（生テキスト）")

    # データソース
    source: str = Field(default="mhlw_kaigo_open_data", description="データソース名")

    # === 将来追加予定（Phase 3: 介護サービス情報公表システムスクレイピング後）===
    # care_manager_count: Optional[int]          # ケアマネジャー人数
    # chief_care_manager_count: Optional[int]    # 主任ケアマネジャー人数
    # employee_total: Optional[int]              # 従業員総数
    # users_total: Optional[int]                 # 利用者総数
    # service_area_text: Optional[str]           # サービス提供エリア（テキスト）
    # operating_policy_text: Optional[str]       # 運営方針テキスト


class OfficeWeb(BaseModel):
    """
    Web補完情報（Google Places API等から取得）

    訪問看護の StationWeb と同一構造。
    office_id フィールドのみ station_id から汎化。
    """

    office_id: str = Field(description="OfficeMaster.office_id と対応")
    website_url: Optional[str] = Field(default=None, description="公式サイトURL（重複保持）")
    google_place_id: Optional[str] = Field(default=None, description="Google Place ID")
    rating: Optional[float] = Field(default=None, description="Google 評価（1.0〜5.0）")
    review_count: Optional[int] = Field(default=None, description="Google レビュー件数")
    photo_url: Optional[str] = Field(default=None, description="Google 写真URL")
    business_status: Optional[str] = Field(
        default=None,
        description="営業状態（OPERATIONAL / CLOSED_PERMANENTLY 等）"
    )


class ScrapeAudit(BaseModel):
    """
    取得監査ログ

    訪問看護の ScrapeAudit と完全同一。
    どのソースからいつ何件取得したかを記録し、データ品質の追跡を可能にする。
    """

    run_id: str = Field(description="実行ID（UUID or タイムスタンプ）")
    source_name: str = Field(description="ソース名（例: mhlw_jigyosho_430）")
    target_url: str = Field(description="取得先URL")
    fetched_at: str = Field(description="取得日時 ISO8601")
    status: str = Field(description="success / error / skipped")
    row_count: Optional[int] = Field(default=None, description="取得行数")
    error_message: Optional[str] = Field(default=None, description="エラーメッセージ")
    file_hash: Optional[str] = Field(default=None, description="ファイルSHA256ハッシュ（改ざん検知）")
    file_path: Optional[str] = Field(default=None, description="保存先パス")
