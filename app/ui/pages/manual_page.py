"""操作说明页：面向新人的内置使用手册。"""

from __future__ import annotations

from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

from app import APP_NAME, APP_VERSION
from app.services.app_context import AppContext

MANUAL_HTML = f"""
<style>
  body {{ font-family: "Microsoft YaHei"; font-size: 13px; color: #2B3A4A; line-height: 1.7; }}
  h1 {{ color: #1F4E79; font-size: 20px; border-bottom: 2px solid #2E75B6; padding-bottom: 6px; }}
  h2 {{ color: #1F4E79; font-size: 16px; margin-top: 22px; }}
  h3 {{ color: #2E75B6; font-size: 14px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
  th, td {{ border: 1px solid #D5DBE1; padding: 6px 10px; font-size: 12px; }}
  th {{ background: #EDF1F5; }}
  code {{ background: #F0F3F6; padding: 1px 5px; border-radius: 3px; }}
  .tip {{ background: #FFF8E6; border-left: 4px solid #F2C14E; padding: 8px 12px; margin: 8px 0; }}
  .warn {{ background: #FDE7E7; border-left: 4px solid #C62828; padding: 8px 12px; margin: 8px 0; }}
</style>

<h1>{APP_NAME} · 操作说明（v{APP_VERSION}）</h1>

<div class="tip"><b>60 秒快速上手：</b>新同事先向管理员要<b>注册激活码</b>，在登录页【注册】开通账号；
之后每天只需要做两件事——① 进【数据更新】页，选自己的针卡，录入"累计测试量 + 当前针长"；
② 平时看【主控面板】的预警，红色/黄色按提示处理即可。其余页面都是管理员或需要时才用到的配置。</div>

<h2>一、首次使用（管理员）</h2>
<ol>
  <li>登录后右上角<b>修改密码</b>；</li>
  <li>进【产品配置】录入产品：片耗（如 0787 = 17146 次/片）、WPH、<b>新卡初始针长</b>、针卡最大测试量（如 480 万次 / 240 万次）、采购提前期；</li>
  <li>进【站点与 WIP】建站点（N1 前段只记数量，N2 记到 CP 时间），录入当前 WIP 片数；</li>
  <li>进【针卡台账】把手上现有针卡逐张<b>新卡入库</b>（建议顺手录入初始数据点，或用【报表导出】页的<b>导入报表数据</b>批量导入旧表格）；</li>
  <li>工程师用激活码在登录页<b>自助注册</b>，管理员可经左下角【用户管理】（需管理密码）查看和维护账号。</li>
</ol>

<h2>二、每日日常：录入数据（数据更新页）</h2>
<p>每次拿到新的测试量/针长数据：【数据更新】→ 搜索并选中针卡 → 改日期 →
填<b>累计测试量</b>（自新卡起，机台计数器累计值）和<b>当前针长</b> → 保存。</p>
<div class="warn"><b>注意：</b>累计测试量必须不小于上一次录入值；针长单位是 um（微米）。
软件会自动提示倒挂、到线等异常。</div>

<h2>三、寿命预测是怎么算的</h2>
<ul>
  <li>每张卡的（累计测试量, 针长）数据点做<b>线性拟合</b>，外推出针长降到报废线（默认 22um）时的累计测试量；</li>
  <li>数据点不足 3 个时，自动借用<b>同产品所有针卡</b>（含已报废卡的完整寿命数据）汇总拟合的平均磨损曲线来预测——数据越多越准；</li>
  <li><b>寿命达成率</b> = 预测报废时测试量 ÷ 厂商额定寿命。低于黄色阈值（默认 90%）或红色阈值（默认 80%）时，说明这张卡到 22um 时到不了额定寿命，会在主控面板预警；</li>
  <li><b>预计报废日期</b>：按该卡最近的消耗速度（次/天）外推，提前 N 天（默认 14 天）在主控面板提醒准备替换卡；</li>
  <li>曲线图在【针卡台账】→ 选中卡片 → <b>详情/磨损曲线</b>：蓝点是实测数据，绿/橙色虚线是拟合预测线，红色虚线是报废线。</li>
</ul>

<h2>四、三卡规则</h2>
<p>每个产品要求至少 3 张<b>在库</b>针卡（在用卡正在机台上消耗，不计入可调配储备）。一张卡可以支持多个产品，会同时给每个产品计数。
缺口会显示在【主控面板 → 三卡规则缺口】和【仓库管理 → 产品库存】页。</p>

<h2>五、需求预估（站点与 WIP 页）</h2>
<p>站点分两级：<b>N1 前段站点</b>距 CP 时间过长，WIP 只记<b>数量</b>（作未来流入量参考，不参与时间推算）；
<b>N2 站点</b>记<b>数量 + 到 CP 时间</b>，按站点顺序（CP前第1站、第2站…）推算未来（默认 14 天）每天到达 CP 的片数，
乘以片耗得到测试量需求，再除以单卡平均剩余寿命，折算出需要准备的针卡张数。
流程：N1 各站点 → N2 各站点 → CP。结果在【主控面板】与报表【需求预估】中查看。</p>

<h2>六、采购管理（闭环流程）</h2>
<ol>
  <li>软件对每个产品计算：<b>预计缺口日期</b>（累计需求超过现有总余量那天）和<b>最晚下单日</b>（缺口日 − 提前期 − 缓冲天数）；</li>
  <li>过最晚下单日 → 红色"立即下单"；7 天内 → 黄色"尽快下单"；</li>
  <li>点<b>按选中建议登记采购单</b>（数量已按建议预填）；</li>
  <li>到货后在采购单上点<b>标记到货</b>，再用【针卡台账 → 新卡入库】把实体卡录入系统；</li>
  <li>计算缺口时会自动扣除"在途"采购数量，不会重复下单。</li>
</ol>
<div class="tip"><b>先仓库后采购：</b>缺卡时先看【仓库管理】各产品在库数，有在库卡就领用校准上机；没有才走采购。</div>

<h2>七、仓库管理</h2>
<ul>
  <li>三种状态：<b>在库</b>（仓库里）→ <b>在用</b>（机台上）→ <b>报废</b>；</li>
  <li>领用上机：在库 → 在用；下机回库：在用 → 在库；报废：任意状态 → 报废（需确认）；</li>
  <li>每次流转都记录操作人和时间，可在【流转与操作日志】查追溯；</li>
  <li>报废的针卡数据保留，其完整寿命数据会继续用于同类型卡的磨损曲线拟合。</li>
</ul>

<h2>八、报表导出与导入</h2>
<p>【报表导出】页可导出四种 Excel：针卡台账、寿命预测、需求预估、采购建议与采购单，
文件保存在数据库目录的 <code>exports</code> 文件夹；也可点击<b>导入报表数据</b>，
选择之前导出的 Excel（自动识别格式），把针卡和最新数据点批量导入系统——
适合初始化系统或从旧表格迁移数据。产品不存在时会自动按名称创建（片耗等参数请再在【产品配置】补全），
针卡已存在时跳过、只补充新的数据点。</p>

<h2>九、部署说明（管理员必读）</h2>
<ul>
  <li>软件是单文件 exe，任何人双击即可运行，无需安装 Python；</li>
  <li><b>推荐部署</b>：把 <code>probe_card_manager.exe</code> 和 <code>config.ini</code> 放到共享盘
      （如 <code>\\\\文件服务器IP\\…</code>），数据默认存在 exe 同级的 <code>data\\probe_card.db</code>；</li>
  <li>如果同事本地拷贝 exe 运行，请编辑 <code>config.ini</code>，把数据库路径指向共享盘：
      <code>[database] db_path = \\\\文件服务器IP\\share\\probe_card.db</code>——
      <b>所有人必须指向同一个文件，数据才互通</b>；</li>
  <li><div class="warn">共享盘必须是局域网文件共享（SMB），不能用 OneDrive/坚果云等同步盘，否则数据库会损坏。</div></li>
  <li>每天首次打开软件会自动备份数据库到 <code>data\\backups\\</code>，默认保留 30 天。</li>
</ul>

<h2>十、常见问题</h2>
<table>
  <tr><th>现象</th><th>处理</th></tr>
  <tr><td>提示 "database is locked"</td><td>多人同时写入，软件会自动排队重试；若频繁出现，错峰保存或联系管理员升级部署方式</td></tr>
  <tr><td>某张卡没有预测结果</td><td>该卡数据点不足且该产品尚无可参考的历史数据，多录入几个数据点即可</td></tr>
  <tr><td>录入测试量提示小于最近记录</td><td>确认为修正数据可直接确认；误操作可在【数据更新】页选中该条记录删除</td></tr>
  <tr><td>忘记密码</td><td>联系管理员经左下角【用户管理】重置</td></tr>
  <tr><td>预测的报废日期明显不合理</td><td>检查最近两次数据点的日期与测试量是否录入正确（速度由最近两次点决定）</td></tr>
  <tr><td>导入报表提示部分行失败</td><td>查看汇总弹窗中的失败原因（常见：缺少针卡名称、片数/测试量不是数字），修正 Excel 后重新导入，已成功的行不会重复导入</td></tr>
</table>
"""


class ManualPage(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setHtml(MANUAL_HTML)
        root.addWidget(browser)

    def refresh(self):
        pass
