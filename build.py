import os
import shutil
import requests
from urllib.parse import quote

# ===================== 飞书配置 =====================
APP_ID = os.getenv("FEISHU_APP_ID", "").strip()
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "").strip()
BASE_TOKEN = os.getenv("FEISHU_BASE_TOKEN", "").strip()
BASE_API = "https://open.feishu.cn/open-apis"

# 启动前校验必填环境变量
_required = {"FEISHU_APP_ID": APP_ID, "FEISHU_APP_SECRET": APP_SECRET, "FEISHU_BASE_TOKEN": BASE_TOKEN}
_missing = [k for k, v in _required.items() if not v]
if _missing:
    print(f"❌ 缺少必填环境变量: {', '.join(_missing)}")
    raise SystemExit(1)

# 多维表格中各数据表的名称（按飞书表格实际名称填写）
TABLE_NAMES = {
    "site_config": "网站设置",
    "carousel": "轮播图",
    "social": "关注我们",
    "categories": "产品分类",
    "products": "全部产品",
    "custom_pages": "通用页"
}

# 站点域名（从飞书「网站设置」表读取）
SITE_DOMAIN = ""
OUTPUT_DIR = "public"
TEMPLATE_DIR = "template"

# ===================== 飞书接口函数 =====================
def get_tenant_token():
    url = f"{BASE_API}/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET})
    data = resp.json()
    if "tenant_access_token" not in data:
        print(f"❌ 飞书认证失败: {data}")
        raise SystemExit(1)
    return data["tenant_access_token"]

def list_tables(token):
    """获取多维表格中所有数据表的 名称→table_id 映射"""
    url = f"{BASE_API}/bitable/v1/apps/{BASE_TOKEN}/tables"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    data = resp.json()
    if data.get("code", -1) != 0:
        print(f"❌ 获取数据表列表失败: {data}")
        raise SystemExit(1)
    return {item["name"]: item["table_id"] for item in data["data"]["items"]}

def get_table_records(token, table_id):
    """分页获取数据表全部记录（按飞书表格拖拽排序顺序返回）"""
    all_items = []
    page_token = None
    while True:
        url = f"{BASE_API}/bitable/v1/apps/{BASE_TOKEN}/tables/{table_id}/records?page_size=500"
        if page_token:
            url += f"&page_token={page_token}"
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers)
        data = resp.json()
        if data.get("code", -1) != 0:
            print(f"❌ 获取记录失败 (table_id={table_id}): {data}")
            raise SystemExit(1)
        all_items.extend(data.get("data", {}).get("items", []))
        page_token = data.get("data", {}).get("page_token")
        if not page_token:
            break
    return all_items

# ===================== 模板渲染 =====================
def load_template(tpl_name):
    path = os.path.join(TEMPLATE_DIR, tpl_name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def render_template(tpl, data):
    for k, v in data.items():
        tpl = tpl.replace(f"{{{{{k}}}}}", str(v))
    return tpl

# ===================== 静态文件生成：robots / sitemap =====================
def gen_robots():
    content = f"""User-agent: *
Allow: /
Sitemap: {SITE_DOMAIN}/sitemap.xml
"""
    path = os.path.join(OUTPUT_DIR, "robots.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def gen_sitemap(all_urls):
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url in all_urls:
        xml += f'  <url><loc>{url}</loc></url>\n'
    xml += '</urlset>'
    path = os.path.join(OUTPUT_DIR, "sitemap.xml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)

# ===================== HTML生成辅助函数 =====================
def mkdir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def s(val, default=""):
    """飞书字段值兼容：列表取首元素，空值给默认值，始终返回字符串"""
    if isinstance(val, list):
        return str(val[0]) if val else default
    if isinstance(val, str):
        return val.strip() or default
    return str(val) if val is not None else default

def _download_one(token, att, save_dir="assets"):
    """下载单个飞书附件到本地，返回 Web 路径"""
    file_token = att.get("file_token", "")
    name = att.get("name", file_token)
    # 优先用附件自带的 url / tmp_url，加认证头下载
    download_url = att.get("url", "") or att.get("tmp_url", "")
    if not download_url and file_token:
        download_url = f"{BASE_API}/drive/v1/medias/{file_token}"
    if download_url:
        local_dir = os.path.join(OUTPUT_DIR, save_dir)
        os.makedirs(local_dir, exist_ok=True)
        ext = os.path.splitext(name)[1] or ".bin"
        local_name = f"{file_token}{ext}" if file_token else f"{name}"
        save_path = os.path.join(local_dir, local_name)
        if not os.path.exists(save_path):
            try:
                resp = requests.get(download_url, headers={"Authorization": f"Bearer {token}"}, stream=True, timeout=60)
                if resp.status_code != 200:
                    err = resp.text[:200]
                    print(f"  ⚠️ 下载失败 ({name}): HTTP {resp.status_code} - {err}")
                    return download_url
                ct = resp.headers.get("Content-Type", "")
                if "json" in ct or "text/html" in ct:
                    err = resp.text[:200]
                    print(f"  ⚠️ 下载失败 ({name}): 响应类型异常 {ct} - {err}")
                    return download_url
                with open(save_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                size_kb = os.path.getsize(save_path) / 1024
                print(f"  ✅ 下载成功: {name} ({size_kb:.1f}KB)")
            except Exception as e:
                print(f"  ⚠️ 下载失败 ({name}): {e}")
                return download_url
        return f"/{save_dir}/{local_name}"
    return download_url or ""

def download_media(token, val, save_dir="assets"):
    """飞书附件下载到本地，字符串URL原样返回"""
    if isinstance(val, list) and val:
        return _download_one(token, val[0], save_dir)
    if isinstance(val, str) and val.strip():
        return val.strip()
    return ""

def download_media_list(token, val, save_dir="assets"):
    """飞书多附件下载，返回 URL 列表"""
    if not isinstance(val, list):
        return [val.strip()] if isinstance(val, str) and val.strip() else []
    return [_download_one(token, att, save_dir) for att in val]

def gen_product_card(p, cat_map):
    """生成单个商品卡片HTML（用于首页/分类页横滚 & 网格）"""
    cat_slug = cat_map.get(p["cat"], {}).get("slug", "")
    img_src = p['img'][0] if p['img'] else ""
    amazon_url = f"https://www.amazon.com/dp/{p['asin']}/" if p['asin'] else p['link']
    return f"""<div class="product-card">
    <a href="/{cat_slug}/{p['slug']}/">
        <img src="{img_src}" alt="{p['title']}" class="product-img">
    </a>
    <div class="product-info">
        <h3 class="product-name"><a href="/{cat_slug}/{p['slug']}/">{p['title']}</a></h3>
        <p class="product-price">${p['price']}</p>
        <a href="{amazon_url}" target="_blank" class="buy-btn">Buy on Amazon</a>
    </div>
</div>
"""

def gen_related_card(p, cat_map):
    """生成相关商品卡片HTML（用于商品详情页底部）"""
    cat_slug = cat_map.get(p["cat"], {}).get("slug", "")
    img_src = p['img'][0] if p['img'] else ""
    amazon_url = f"https://www.amazon.com/dp/{p['asin']}/" if p['asin'] else p['link']
    return f"""<div class="related-card">
    <a href="/{cat_slug}/{p['slug']}/">
        <img src="{img_src}" alt="{p['title']}" class="related-img">
    </a>
    <div class="related-info">
        <h3 class="related-name"><a href="/{cat_slug}/{p['slug']}/">{p['title']}</a></h3>
        <p class="related-price">${p['price']}</p>
        <a href="{amazon_url}" target="_blank" class="related-buy-btn">Buy on Amazon</a>
    </div>
</div>
"""

def gen_slider_html(carousel_data, token):
    """生成轮播图HTML（.slider 结构，与 script.js 配合）"""
    if not carousel_data:
        return ""
    slides_html = ""
    dots_html = ""
    for idx, item in enumerate(carousel_data):
        fd = item["fields"]
        img = download_media(token, fd.get("轮播图片"))
        link = s(fd.get("图片链接"), "#")
        alt_text = s(fd.get("图片文本alt"), f"Banner {idx+1}")
        active = "active" if idx == 0 else ""
        slides_html += f'<div class="slide {active}"><a href="{link}" target="_blank"><img src="{img}" alt="{alt_text}"></a></div>\n'
        dots_html += f'<div class="slider-dot {active}" onclick="goToSlide({idx})"></div>\n'

    return f"""<div class="slider">
  <button class="slider-prev" onclick="prevSlide()"><i class="fas fa-chevron-left"></i></button>
  <button class="slider-next" onclick="nextSlide()"><i class="fas fa-chevron-right"></i></button>
  {slides_html}
  <div class="slider-dots">
    {dots_html}
  </div>
</div>
"""

# ===================== 页面生成主逻辑 =====================
def main():
    mkdir(OUTPUT_DIR)
    all_sitemap_urls = []

    # 获取飞书全量数据
    token = get_tenant_token()
    table_map = list_tables(token)  # {"网站设置": "tblxxx", "全部产品": "tblyyy", ...}
    site_config = get_table_records(token, table_map[TABLE_NAMES["site_config"]])
    carousel_data = get_table_records(token, table_map[TABLE_NAMES["carousel"]])
    social_data = get_table_records(token, table_map[TABLE_NAMES["social"]])
    cat_list = get_table_records(token, table_map[TABLE_NAMES["categories"]])
    print(f"  分类表字段: {list(cat_list[0]['fields'].keys()) if cat_list else 'empty'}")
    prod_list = get_table_records(token, table_map[TABLE_NAMES["products"]])
    page_list = get_table_records(token, table_map[TABLE_NAMES["custom_pages"]])
    # 按「序号」字段升序排列
    for cat in cat_list:
        fd = cat.get("fields", {})
        print(f"    {fd.get('分类title', '?')}: 序号={fd.get('序号', 'N/A')}")
    carousel_data.sort(key=lambda x: int(x.get("fields", {}).get("序号", 9999)))
    social_data.sort(key=lambda x: int(x.get("fields", {}).get("序号", 9999)))
    cat_list.sort(key=lambda x: int(x.get("fields", {}).get("序号", 9999)))
    prod_list.sort(key=lambda x: int(x.get("fields", {}).get("序号", 9999)))
    page_list.sort(key=lambda x: int(x.get("fields", {}).get("序号", 9999)))

    # 基础站点信息（来自「网站设置」表）
    cfg = site_config[0]["fields"] if site_config else {}
    site_name = s(cfg.get("品牌名称"), "Site")
    site_title = s(cfg.get("网站title"), site_name)
    site_logo = download_media(token, cfg.get("网站logo"))
    logo_display = s(cfg.get("logo显示"), "都显示")
    # 根据 logo显示 设置生成 header / footer 的 logo HTML
    if logo_display == "只显示logo":
        _hidden_h1 = '<h1 style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap"><a href="/">' + site_name + '</a></h1>'
        header_logo_html = '<div class="logo"><a href="/"><img src="' + site_logo + '" alt="' + site_name + '"></a>' + _hidden_h1 + '</div>'
        footer_logo_html = header_logo_html
    elif logo_display == "只显示品牌名称":
        header_logo_html = '<div class="logo"><h1><a href="/">' + site_name + '</a></h1></div>'
        footer_logo_html = header_logo_html
    else:  # 都显示
        header_logo_html = '<div class="logo"><a href="/"><img src="' + site_logo + '" alt="' + site_name + '"></a><h1><a href="/">' + site_name + '</a></h1></div>'
        footer_logo_html = header_logo_html
    og_image = download_media(token, cfg.get("og图片"))
    site_keywords = s(cfg.get("网站keywords"))
    site_desc = s(cfg.get("网站description"))
    global SITE_DOMAIN
    SITE_DOMAIN = s(cfg.get("网站url"))

    # 顶部通知 & 自定义代码（也来自「网站设置」表）
    notice_html = s(cfg.get("顶部通知栏"))
    head_code = s(cfg.get("自定义head代码"))
    foot_code = s(cfg.get("全站底部-自定义代码"))
    home_custom_code = s(cfg.get("首页底部-自定义代码"))
    primary_color = s(cfg.get("主色"), "#133CD1")
    secondary_color = s(cfg.get("辅助色"), "#00d2d3")
    copyright_text = s(cfg.get("版权信息"), f"&copy; 2011 - 2026 The {site_name} Company. All rights reserved.")

    # 字体设置（格式如 "Inter,700"）
    heading_font_raw = s(cfg.get("标题字体和字重"), "Noto Sans,700")
    body_font_raw = s(cfg.get("正文字体和字重"), "Noto Sans,400")
    heading_font, heading_weight = heading_font_raw.split(",")[0].strip(), heading_font_raw.split(",")[1].strip() if "," in heading_font_raw else "700"
    body_font, body_weight = body_font_raw.split(",")[0].strip(), body_font_raw.split(",")[1].strip() if "," in body_font_raw else "400"
    # 生成 Google Fonts URL（合并所有字重）
    weights = sorted(set([heading_weight, body_weight, "400"]))  # 确保包含400
    weights_str = ";".join(weights)
    google_fonts_url = f"https://fonts.googleapis.com/css2?family={heading_font.replace(' ', '+')}:wght@{weights_str}&family={body_font.replace(' ', '+')}:wght@{weights_str}&display=swap"

    # Favicon（来自「网站设置」表的附件字段，直接取URL）
    favicon_url = download_media(token, cfg.get("Favicon"))

    # 生成 favicon <link> 标签（根据扩展名自动匹配 type）
    favicon_tag = ""
    if favicon_url:
        ext = favicon_url.rsplit(".", 1)[-1].split("?")[0].lower() if "." in favicon_url else ""
        mime_map = {"svg": "image/svg+xml", "ico": "image/x-icon", "png": "image/png", "gif": "image/gif", "jpg": "image/jpeg", "jpeg": "image/jpeg"}
        mime = mime_map.get(ext, "")
        favicon_tag = f'<link rel="icon" href="{favicon_url}"' + (f' type="{mime}">' if mime else '>')

    # 社交媒体链接（来自「关注我们」表）
    # 社交名称 → 图标映射
    social_icon_map = {
        "facebook": "fab fa-facebook-f",
        "twitter": "fab fa-twitter",
        "x": "fab fa-x-twitter",
        "instagram": "fab fa-instagram",
        "youtube": "fab fa-youtube",
        "tiktok": "fab fa-tiktok",
        "pinterest": "fab fa-pinterest",
        "linkedin": "fab fa-linkedin-in",
        "whatsapp": "fab fa-whatsapp",
        "telegram": "fab fa-telegram",
        "wechat": "fab fa-weixin",
        "微信": "fab fa-weixin",
        "amazon": "fab fa-amazon",
    }
    social_links_html = ""
    for item in social_data:
        fd = item["fields"]
        url = s(fd.get("社交网址"))
        name = s(fd.get("社交名称")).lower()
        # 社交网址为空则不显示
        if not url:
            continue
        # 根据社交名称匹配图标，找不到则用默认图标
        icon = social_icon_map.get(name, "fas fa-link")
        social_links_html += f'<a href="{url}" target="_blank"><i class="{icon}"></i></a>\n'

    # 轮播图HTML（使用 .slider 结构）
    carousel_html = gen_slider_html(carousel_data, token)

    # 分类导航（头部 + 页脚）
    cat_nav_html = ""
    cat_nav_footer_html = ""
    cat_list_html = ""
    cat_map = {}        # {title: {slug, desc, kw}}
    cat_id_map = {}     # {record_id: {slug, desc, title}}
    for cat in cat_list:
        fd = cat["fields"]
        rid = cat.get("record_id", "")
        slug = s(fd.get("分类slug"))
        title = s(fd.get("分类title"))
        desc = s(fd.get("分类description"))
        kw = s(fd.get("分类keywords"))
        cat_map[title] = {"slug": slug, "desc": desc, "title": title, "kw": kw}
        if rid:
            cat_id_map[rid] = {"slug": slug, "desc": desc, "title": title}
        cat_nav_html += f'<li><a href="/{slug}/">{title}</a></li>'
        cat_nav_footer_html += f'<li><a href="/{slug}/">{title}</a></li>'
        cat_list_html += f'<a href="/{slug}/">{title}</a>'
    print(f"  分类映射: {list(cat_map.keys())}")

    # 自定义页面导航（头部 + 页脚）
    page_nav_html = ""
    page_nav_footer_html = ""
    page_map = {}
    for page in page_list:
        fd = page["fields"]
        slug = s(fd.get("通用slug"))
        title = s(fd.get("通用title"))
        page_map[slug] = {"title": title, "content": s(fd.get("正文")), "kw": s(fd.get("通用keywords")), "desc": s(fd.get("通用description"))}
        page_nav_html += f'<li><a href="/{slug}/">{title}</a></li>'
        page_nav_footer_html += f'<li><a href="/{slug}/">{title}</a></li>'

    # 商品数据整理
    prod_map = []
    no_match_cats = set()
    for prod in prod_list:
        fd = prod["fields"]
        raw_cat = fd.get("产品分类", "")
        # 关联字段匹配：先尝试 record_id，再尝试 text 文本
        cat_info = None
        if isinstance(raw_cat, list) and raw_cat:
            first = raw_cat[0]
            if isinstance(first, dict):
                # 飞书关联字段格式：{'record_ids': [...], 'text': '...'}
                rec_ids = first.get("record_ids", [])
                if rec_ids and rec_ids[0] in cat_id_map:
                    cat_info = cat_id_map[rec_ids[0]]
                if not cat_info:
                    text = first.get("text", "") or first.get("text_arr", [""])[0] if first.get("text_arr") else ""
                    if text and text in cat_map:
                        cat_info = cat_map[text]
            elif isinstance(first, str) and first in cat_id_map:
                # record_id 字符串
                cat_info = cat_id_map[first]
            elif isinstance(first, list) and len(first) > 0:
                # 嵌套列表
                rid = str(first[0])
                if rid in cat_id_map:
                    cat_info = cat_id_map[rid]
        # title 文本 fallback 匹配
        cat_text = s(raw_cat)
        if not cat_info and cat_text in cat_map:
            cat_info = cat_map[cat_text]
        if not cat_info:
            no_match_cats.add(repr(raw_cat))
            cat_info = {"slug": "", "desc": "", "title": ""}
        prod_map.append({
            "cat": cat_info["title"],
            "slug": s(fd.get("产品slug")),
            "title": s(fd.get("产品title")),
            "img": download_media_list(token, fd.get("产品图片"))[::-1] + [u.strip() for u in s(fd.get("产品图片url"), "").split(",") if u.strip()],
            "price": s(fd.get("单价", "0")),
            "asin": s(fd.get("asin")),
            "content": s(fd.get("产品简介")),
            "desc": s(fd.get("产品description")) or s(fd.get("产品简介")),
            "keywords": s(fd.get("产品keywords")),
            "link": s(fd.get("跳转链接", "#")),
            "is_new": s(fd.get("新品", "否")) == "是",
            "is_bestseller": s(fd.get("畅销品", "否")) == "是"
        })
    if no_match_cats:
        print(f"  ⚠️ 以下产品分类未匹配到分类表: {no_match_cats}")
        print(f"     分类表可用key: {list(cat_map.keys())} / {list(cat_id_map.keys())}")

    # 筛选新品Top30、畅销品Top30
    new_products = [p for p in prod_map if p["is_new"]][:30]
    bestseller_products = [p for p in prod_map if p["is_bestseller"]][:30]

    # 加载公共模板
    tpl_header_index = load_template("header_index.html")
    tpl_header_category = load_template("header_category.html")
    tpl_header_product = load_template("header_product.html")
    tpl_header_custom = load_template("header_custom.html")
    tpl_footer = load_template("footer.html")
    tpl_index = load_template("index.html")
    tpl_category = load_template("category.html")
    tpl_product = load_template("product.html")
    tpl_custom = load_template("custompage.html")

    # ===================== 渲染公共 Footer =====================
    footer_data = {
        "site_name": site_name,
        "site_logo": site_logo,
        "footer_logo_html": footer_logo_html,
        "site_desc": site_desc,
        "SITE_DOMAIN": SITE_DOMAIN,
        "social_links": social_links_html,
        "category_nav_footer": cat_nav_footer_html,
        "custom_page_nav_footer": page_nav_footer_html,
        "custom_foot_code": foot_code,
        "copyright_text": copyright_text
    }
    footer_rendered = render_template(tpl_footer, footer_data)

    # 公共 Header 基础数据（每个页面单独渲染 SEO）
    base_header_data = {
        "site_name": site_name,
        "site_title": site_title,
        "site_logo": site_logo,
        "header_logo_html": header_logo_html,
        "og_image": og_image,
        "SITE_DOMAIN": SITE_DOMAIN,
        "google_fonts_url": google_fonts_url,
        "favicon_tag": favicon_tag,
        "top_notice": notice_html,
        "category_nav": cat_nav_html,
        "custom_page_nav": page_nav_html,
        "custom_head_code": head_code
    }

    def make_header(tpl, seo):
        """生成带独立 SEO 的 header HTML，seo 为页面专属变量字典"""
        d = dict(base_header_data)
        d.update(seo)
        return render_template(tpl, d)

    # ===================== 生成首页 =====================
    prod_item_html = "".join(gen_product_card(p, cat_map) for p in prod_map)
    new_prod_html = "".join(gen_product_card(p, cat_map) for p in new_products)
    bestseller_prod_html = "".join(gen_product_card(p, cat_map) for p in bestseller_products)
    index_header = make_header(tpl_header_index, {
        "index_keywords": site_keywords,
        "index_description": site_desc
    })

    index_data = {
        "header": index_header,
        "footer": footer_rendered,
        "carousel_html": carousel_html,
        "category_list": cat_list_html,
        "product_list": prod_item_html,
        "new_product_list": new_prod_html,
        "bestseller_list": bestseller_prod_html,
        "home_custom_code": home_custom_code
    }
    index_html = render_template(tpl_index, index_data)
    index_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)
    all_sitemap_urls.append(f"{SITE_DOMAIN}/")

    # ===================== 生成分类列表页 + 商品详情页 =====================
    for cat_name, cat_info in cat_map.items():
        cat_slug = cat_info["slug"]
        cat_desc = cat_info["desc"]
        cat_dir = os.path.join(OUTPUT_DIR, cat_slug)
        mkdir(cat_dir)

        # 当前分类下商品（新发布的显示在前面，反序）
        cat_prods = [p for p in prod_map if p["cat"] == cat_name][::-1]
        cat_prod_html = "".join(gen_product_card(p, cat_map) for p in cat_prods)

        # 生成分类列表页
        cat_header = make_header(tpl_header_category, {
            "category_title": cat_name,
            "category_keywords": cat_info.get("kw", ""),
            "category_description": cat_desc
        })
        cat_page_data = {
            "header": cat_header,
            "footer": footer_rendered,
            "category_name": cat_name,
            "category_desc": cat_desc,
            "category_product_count": str(len(cat_prods)),
            "category_product_list": cat_prod_html
        }
        cat_html = render_template(tpl_category, cat_page_data)
        cat_file = os.path.join(cat_dir, "index.html")
        with open(cat_file, "w", encoding="utf-8") as f:
            f.write(cat_html)
        all_sitemap_urls.append(f"{SITE_DOMAIN}/{cat_slug}/")

        # 生成当前分类下所有商品详情页
        for p in cat_prods:
            prod_slug = p["slug"]
            prod_dir = os.path.join(cat_dir, prod_slug)
            mkdir(prod_dir)

            # 商品多图处理（p["img"] 现在是图片列表）
            images = p["img"] if isinstance(p["img"], list) else [p["img"]] if p["img"] else []

            images_html = ""
            dots_html = ""
            thumbnails_html = ""
            for idx, img_src in enumerate(images):
                active = "active" if idx == 0 else ""
                images_html += f'<img src="{img_src}" alt="Product {idx+1}" class="carousel-img {active}">\n'
                dots_html += f'<span class="dot {active}" onclick="goToSlide({idx})"></span>\n'
                thumbnails_html += f'<div class="thumbnail {active}" onclick="changeImage({idx+1})"><img src="{img_src}" alt="Thumbnail {idx+1}"></div>\n'

            # 相关商品（同分类下其他商品 + 其他分类商品补充，最多15个）
            related = [rp for rp in cat_prods if rp["slug"] != prod_slug][:15]
            if len(related) < 15:
                other_prods = [rp for rp in prod_map if rp["cat"] != cat_name and rp["slug"] != prod_slug]
                related += other_prods[:15 - len(related)]
            related_html = "".join(gen_related_card(rp, cat_map) for rp in related)

            prod_page_data = {
                "header": make_header(tpl_header_product, {
                    "product_title": p["title"],
                    "product_keywords": p["keywords"],
                    "product_description": p["desc"]
                }),
                "footer": footer_rendered,
                "product_title": p["title"],
                "product_img": p["img"][0] if p["img"] else "",
                "product_price": p["price"],
                "product_asin": p["asin"],
                "product_content": p["content"],
                "product_amazon_link": p["link"],
                "product_images_html": images_html,
                "product_dots_html": dots_html,
                "product_thumbnails_html": thumbnails_html,
                "category_slug": cat_slug,
                "category_name": cat_name,
                "related_products": related_html
            }
            prod_html = render_template(tpl_product, prod_page_data)
            prod_file = os.path.join(prod_dir, "index.html")
            with open(prod_file, "w", encoding="utf-8") as f:
                f.write(prod_html)
            all_sitemap_urls.append(f"{SITE_DOMAIN}/{cat_slug}/{prod_slug}/")

    # ===================== 生成自定义页面 =====================
    for slug, page_info in page_map.items():
        page_dir = os.path.join(OUTPUT_DIR, slug)
        mkdir(page_dir)
        page_data = {
            "header": make_header(tpl_header_custom, {
                "custom_title": page_info["title"],
                "custom_keywords": page_info.get("kw", ""),
                "custom_description": page_info.get("desc", "")
            }),
            "footer": footer_rendered,
            "page_title": page_info["title"],
            "page_content": page_info["content"]
        }
        page_html = render_template(tpl_custom, page_data)
        page_file = os.path.join(page_dir, "index.html")
        with open(page_file, "w", encoding="utf-8") as f:
            f.write(page_html)
        all_sitemap_urls.append(f"{SITE_DOMAIN}/{slug}/")

    # ===================== 渲染静态资源 & CNAME =====================
    # style.css 用模板渲染（支持颜色占位符）
    tpl_css = load_template("style.css")
    css_data = {
            "primary_color": primary_color,
            "secondary_color": secondary_color,
            "heading_font": heading_font,
            "body_font": body_font
        }
    css_rendered = render_template(tpl_css, css_data)
    with open(os.path.join(OUTPUT_DIR, "style.css"), "w", encoding="utf-8") as f:
        f.write(css_rendered)
    shutil.copy(os.path.join(TEMPLATE_DIR, "script.js"), os.path.join(OUTPUT_DIR, "script.js"))
    if os.path.exists("CNAME"):
        shutil.copy("CNAME", os.path.join(OUTPUT_DIR, "CNAME"))
    print("✅ style.css、script.js、CNAME 已复制到 public/")

    # ===================== 生成 robots.txt & sitemap.xml =====================
    gen_robots()
    gen_sitemap(all_sitemap_urls)
    print("✅ 全部页面生成完成！")

if __name__ == "__main__":
    main()
