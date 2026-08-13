"""RoiSiteConfig 读写与传给 ROI 脚本的定值字典。"""
from __future__ import annotations

from .marketplace import (
    MARKETPLACE_UK,
    MARKETPLACE_US,
    normalize_marketplace,
    platform_commission_percent,
)
from .models import RoiSiteConfig


def ensure_site_config(marketplace: str | None) -> RoiSiteConfig:
    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    defaults = {
        'platform_commission': platform_commission_percent(mp),
        'default_refund_rate': 10.0,
        'default_fba_fee': 5.0,
        'default_unit_purchase': 10.0,
        'batch_size': 20,
        'asin_delay_min_sec': 1.0,
        'asin_delay_max_sec': 3.0,
        'batch_delay_min_sec': 4.0,
        'batch_delay_max_sec': 8.0,
        'max_ban_rotations_per_run': 30,
        'consecutive_fail_pause': 10,
        'max_ban_retries_per_asin': 3,
    }
    obj, _ = RoiSiteConfig.objects.get_or_create(marketplace=mp, defaults=defaults)
    return obj


def ensure_all_site_configs() -> None:
    ensure_site_config(MARKETPLACE_US)
    ensure_site_config(MARKETPLACE_UK)


def roi_defaults_dict(marketplace: str | None) -> dict:
    """供 seller_wizard_main / save_roi_us_pack 使用的定值。"""
    cfg = ensure_site_config(marketplace)
    return {
        'platform_commission': float(cfg.platform_commission),
        'default_refund_rate': float(cfg.default_refund_rate),
        'default_fba_fee': float(cfg.default_fba_fee),
        'default_unit_purchase': float(cfg.default_unit_purchase),
    }


def config_to_api_dict(cfg: RoiSiteConfig) -> dict:
    return {
        'marketplace': cfg.marketplace,
        'platform_commission': cfg.platform_commission,
        'default_refund_rate': cfg.default_refund_rate,
        'default_fba_fee': cfg.default_fba_fee,
        'default_unit_purchase': cfg.default_unit_purchase,
        'batch_size': cfg.batch_size,
        'asin_delay_min_sec': cfg.asin_delay_min_sec,
        'asin_delay_max_sec': cfg.asin_delay_max_sec,
        'batch_delay_min_sec': cfg.batch_delay_min_sec,
        'batch_delay_max_sec': cfg.batch_delay_max_sec,
        'max_ban_rotations_per_run': cfg.max_ban_rotations_per_run,
        'consecutive_fail_pause': cfg.consecutive_fail_pause,
        'max_ban_retries_per_asin': cfg.max_ban_retries_per_asin,
        'exchange_rate_override': cfg.exchange_rate_override,
        'updated_at': cfg.updated_at.isoformat() if cfg.updated_at else None,
    }
