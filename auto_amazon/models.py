from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    """扩展用户：记录注册审核状态（普通用户需超级管理员通过后方可登录）。"""

    class Status(models.TextChoices):
        PENDING = 'pending', '待审核'
        APPROVED = 'approved', '已通过'
        REJECTED = 'rejected', '已拒绝'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    registration_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    reviewed_at = models.DateTimeField('审核时间', null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='registration_reviews_done',
        verbose_name='审核人',
    )

    class Meta:
        verbose_name = '用户资料'
        verbose_name_plural = '用户资料'

    def __str__(self) -> str:
        return f'{self.user.username} · {self.get_registration_status_display()}'


class AsinDashboardRow(models.Model):
    """上传分析后的 ASIN 行数据（每行一个 ASIN）。"""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='asin_rows',
    )
    asin = models.CharField(max_length=32, db_index=True)
    profit_margin = models.FloatField('利润率(%)', null=True, blank=True)
    ranking_percent = models.FloatField('广告难度', null=True, blank=True)
    ops_difficulty_1 = models.TextField('运营难度1', blank=True)
    ops_difficulty_2 = models.TextField('运营难度2', blank=True)
    ops_difficulty_3 = models.TextField('运营难度3', blank=True)
    unit_purchase = models.FloatField('单价', null=True, blank=True)
    monthly_results = models.FloatField('体量', null=True, blank=True)
    profit_per_order = models.FloatField('利润额', null=True, blank=True)
    monthly_profit1 = models.FloatField('产品等级(原始值)', null=True, blank=True)
    monthly_sales_total = models.FloatField('月销售总额', null=True, blank=True)
    head_distance = models.FloatField('头程价格', null=True, blank=True)
    actual_cost = models.FloatField('成本', null=True, blank=True)
    head_actual_total = models.FloatField('成本+头程', null=True, blank=True)
    ad_removed_roi = models.FloatField('去广告投产比', null=True, blank=True)
    product_grade = models.CharField('产品等级', max_length=1)
    sales_trend_json = models.TextField('趋势 JSON', blank=True)
    exchange_rate = models.FloatField('汇率', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', 'asin']
        verbose_name = 'ASIN 分析行'
        verbose_name_plural = 'ASIN 分析行'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'asin'],
                name='uniq_asin_dashboard_user_asin',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.asin} · {self.user_id}'


class AsinFolderAssignment(models.Model):
    """ASIN 文件夹（media/file/<ASIN>/）分配给哪些用户；由超级管理员维护。"""

    asin = models.CharField(max_length=32, unique=True, db_index=True)
    assignees = models.ManyToManyField(
        User,
        related_name='asin_folder_assignments',
        blank=True,
    )
    assigned_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='asin_folder_assignments_created',
        verbose_name='分配人',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'ASIN 文件夹分配'
        verbose_name_plural = 'ASIN 文件夹分配'

    def __str__(self) -> str:
        return self.asin


class AsinRoiPackVerification(models.Model):
    """用户在 Excel 中对某 ASIN 目录下 ROI-US-pack 表点击「确认校验」后记录；用于看板/数据审核展示「是否校验」。"""

    asin = models.CharField(max_length=32, unique=True, db_index=True)
    verified_at = models.DateTimeField(auto_now=True)
    verified_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='roi_pack_verifications',
        verbose_name='确认人',
    )

    class Meta:
        verbose_name = 'ROI 表校验确认'
        verbose_name_plural = 'ROI 表校验确认'

    def __str__(self) -> str:
        return self.asin


class AsinDataUpdateStamp(models.Model):
    """记录 ASIN 数据最近一次更新时刻（每次重算都会刷新）。"""

    asin = models.CharField(max_length=32, unique=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'ASIN 数据更新时间'
        verbose_name_plural = 'ASIN 数据更新时间'

    def __str__(self) -> str:
        return self.asin


class ImportedMediaPath(models.Model):
    """记录用户通过数据审核导入到 media/file 下的路径（文件或目录）。"""

    # MySQL 唯一索引与 CharField 建议 <=255；常见 ASIN 相对路径足够
    rel_path = models.CharField(max_length=255, unique=True, db_index=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='imported_media_paths',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '导入文件路径'
        verbose_name_plural = '导入文件路径'

    def __str__(self) -> str:
        return self.rel_path
