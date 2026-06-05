import os
import re
import requests
from urllib.parse import quote

# ===================== 飞书配置 =====================
APP_ID = os.getenv("FEISHU_APP_ID")
APP_SECRET = os.getenv("FEISHU_APP_SECRET")
BASE_TOKEN = os.getenv("FEISHU_BASE_TOKEN")
BASE_API = "https://open.feishu.cn/open-apis"

# 多维表格中各数据表的名称（按飞书表格实际名称填写）
TABLE_NAMES = {
    "site_config": "网站设置",
    "carousel": "轮播图",
    "social": "关注我们",
    "categories": "产品分类",
    "products": "全部产品",
    "custom_pages": "通用页面"
}

# 站点域名（从飞书「网站设置」表读取）
SITE_DOMAIN = ""
OUTPUT_DIR = "public"
TEMPLATE_DIR = "template"

# ===================== 飞书接口函数 =====================
def get_tenant_token():
    url = f"{BASE_API}/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET})
    return resp.json()["tenant_access_token"]

def list_tables(token):
    """获取多维表格中所有数据表的 名称→table_id 映射"""
    url = f"{BASE_API}/bitable/v1/apps/{BASE_TOKEN}/tables"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    items = resp.json()["data"]["items"]
    return {item["name"]: item["table_id"] for item in items}

def get_table_records(token, table_id):
    """分页获取数据表全部记录"""
    all_items = []
    page_token = None
    while True:
        url = f"{BASE_API}/bitable/v1/apps/{BASE_TOKEN}/tables/{table_id}/records?page_size=500"
        if page_token:
            url += f"&page_token={page_token}"
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers)
        data = resp.json()["data"]
        all_items.extend(data.get("items", []))
        page_token = data.get("page_token")
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

def gen_product_card(p, cat_map):
    """生成单个商品卡片HTML（用于首页/分类页横滚 & 网格）"""
    cat_slug = cat_map.get(p["cat"], {}).get("slug", "")
    return f"""<div class="product-card">
    <a href="/{cat_slug}/{p['slug']}/">
        <img src="{p['img']}" alt="{p['title']}">
    </a>
    <div class="product-info">
        <h3 class="product-name"><a href="/{cat_slug}/{p['slug']}/">{p['title']}</a></h3>
        <p class="product-price">${p['price']}</p>
        <a href="{p['link']}" target="_blank" class="buy-btn">Buy on Amazon</a>
    </div>
</div>
"""

def gen_related_card(p, cat_map):
    """生成相关商品卡片HTML（用于商品详情页底部）"""
    cat_slug = cat_map.get(p["cat"], {}).get("slug", "")
    return f"""<div class="related-card">
    <a href="/{cat_slug}/{p['slug']}/">
        <img src="{p['img']}" alt="{p['title']}" class="related-img">
    </a>
    <div class="related-info">
        <h3 class="related-name"><a href="/{cat_slug}/{p['slug']}/">{p['title']}</a></h3>
        <p class="related-price">${p['price']}</p>
        <a href="{p['link']}" target="_blank" class="related-buy-btn">Buy on Amazon</a>
    </div>
</div>
"""

def gen_slider_html(carousel_data):
    """生成轮播图HTML（.slider 结构，与 script.js 配合）"""
    if not carousel_data:
        return ""
    slides_html = ""
    dots_html = ""
    for idx, item in enumerate(carousel_data):
        fd = item["fields"]
        img = fd.get("轮播图片", "")
        link = fd.get("图片链接", "#")
        active = "active" if idx == 0 else ""
        slides_html += f'<div class="slide {active}"><a href="{link}" target="_blank"><img src="{img}" alt="Banner {idx+1}"></a></div>\n'
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

    # 1. 获取飞书全量数据
    token = get_tenant_token()
    table_map = list_tables(token)  # {"网站设置": "tblxxx", "全部产品": "tblyyy", ...}
    site_config = get_table_records(token, table_map[TABLE_NAMES["site_config"]])
    carousel_data = get_table_records(token, table_map[TABLE_NAMES["carousel"]])
    social_data = get_table_records(token, table_map[TABLE_NAMES["social"]])
    cat_list = get_table_records(token, table_map[TABLE_NAMES["categories"]])
    prod_list = get_table_records(token, table_map[TABLE_NAMES["products"]])
    page_list = get_table_records(token, table_map[TABLE_NAMES["custom_pages"]])

    # 基础站点信息（来自「网站设置」表）
    cfg = site_config[0]["fields"] if site_config else {}
    site_name = cfg.get("网站名称", "Site")
    site_logo = cfg.get("网站logo", "")
    site_keywords = cfg.get("网站keywords", "")
    site_desc = cfg.get("网站description", "")
    global SITE_DOMAIN
    SITE_DOMAIN = cfg.get("网站url", "")

    # 顶部通知 & 自定义代码（也来自「网站设置」表）
    notice_html = cfg.get("通知内容", "")
    head_code = cfg.get("自定义head代码", "")
    foot_code = cfg.get("自定义foot代码", "")

    # Favicon（来自「网站设置」表的附件字段，直接取URL）
    favicon_url = ""
    favicon_field = cfg.get("Favicon")
    if favicon_field:
        if isinstance(favicon_field, list) and len(favicon_field) > 0:
            # 附件类型：取 url 或 tmp_url
            att = favicon_field[0]
            favicon_url = att.get("url", "") or att.get("tmp_url", "")
        elif isinstance(favicon_field, str) and favicon_field.strip():
            favicon_url = favicon_field.strip()

    # 生成 favicon <link> 标签（根据扩展名自动匹配 type）
    favicon_tag = ""
    if favicon_url:
        ext = favicon_url.rsplit(".", 1)[-1].split("?")[0].lower() if "." in favicon_url else ""
        mime_map = {"svg": "image/svg+xml", "ico": "image/x-icon", "png": "image/png", "gif": "image/gif", "jpg": "image/jpeg", "jpeg": "image/jpeg"}
        mime = mime_map.get(ext, "")
        favicon_tag = f'<link rel="icon" href="{favicon_url}"' + (f' type="{mime}">' if mime else '>')

    # 社交媒体链接（来自「关注我们」表）
    social_links_html = ""
    for item in social_data:
        fd = item["fields"]
        url = fd.get("链接", "#")
        icon = fd.get("图标", "fas fa-link")
        social_links_html += f'<a href="{url}" target="_blank"><i class="{icon}"></i></a>\n'

    # 轮播图HTML（使用 .slider 结构）
    carousel_html = gen_slider_html(carousel_data)

    # 分类导航（头部 + 页脚）
    cat_nav_html = ""
    cat_nav_footer_html = ""
    cat_list_html = ""
    cat_map = {}
    for cat in cat_list:
        fd = cat["fields"]
        slug = fd.get("分类slug", "")
        title = fd.get("分类title", "")
        desc = fd.get("分类description", "")
        cat_map[title] = {"slug": slug, "desc": desc}
        cat_nav_html += f'<li><a href="/{slug}/">{title}</a></li>'
        cat_nav_footer_html += f'<li><a href="/{slug}/">{title}</a></li>'
        cat_list_html += f'<a href="/{slug}/">{title}</a>'

    # 自定义页面导航（头部 + 页脚）
    page_nav_html = ""
    page_nav_footer_html = ""
    page_map = {}
    for page in page_list:
        fd = page["fields"]
        slug = fd.get("页面slug", "")
        title = fd.get("页面title", "")
        page_map[slug] = {"title": title, "content": fd.get("正文", ""), "kw": fd.get("分类keywords", ""), "desc": fd.get("分类description", "")}
        page_nav_html += f'<li><a href="/{slug}/">{title}</a></li>'
        page_nav_footer_html += f'<li><a href="/{slug}/">{title}</a></li>'

    # 商品数据整理
    prod_map = []
    for prod in prod_list:
        fd = prod["fields"]
        prod_map.append({
            "cat": fd.get("产品分类", ""),
            "slug": fd.get("产品slug", ""),
            "title": fd.get("产品title", ""),
            "img": fd.get("商品图片", ""),
            "price": fd.get("单价", "0"),
            "asin": fd.get("asin", ""),
            "content": fd.get("产品简介", ""),
            "link": fd.get("跳转链接", "#"),
            "is_new": fd.get("新品", "否") == "是",
            "is_bestseller": fd.get("畅销品", "否") == "是",
            "images": fd.get("商品图片列表", "")
        })

    # 筛选新品Top30、畅销品Top30
    new_products = [p for p in prod_map if p["is_new"]][:30]
    bestseller_products = [p for p in prod_map if p["is_bestseller"]][:30]

    # 加载公共模板
    tpl_header = load_template("header.html")
    tpl_footer = load_template("footer.html")
    tpl_index = load_template("index.html")
    tpl_category = load_template("category.html")
    tpl_product = load_template("product.html")
    tpl_custom = load_template("custompage.html")

    # ===================== 渲染公共 Header & Footer =====================
    header_data = {
        "page_title": "Home",
        "site_name": site_name,
        "page_keywords": site_keywords,
        "page_desc": site_desc,
        "site_logo": site_logo,
        "favicon_tag": favicon_tag,
        "top_notice": notice_html,
        "category_nav": cat_nav_html,
        "custom_page_nav": page_nav_html,
        "custom_head_code": head_code
    }
    header_rendered = render_template(tpl_header, header_data)

    footer_data = {
        "site_name": site_name,
        "site_logo": site_logo,
        "site_desc": site_desc,
        "social_links": social_links_html,
        "category_nav_footer": cat_nav_footer_html,
        "custom_page_nav_footer": page_nav_footer_html,
        "custom_foot_code": foot_code
    }
    footer_rendered = render_template(tpl_footer, footer_data)

    # ===================== 1. 生成首页 =====================
    prod_item_html = "".join(gen_product_card(p, cat_map) for p in prod_map)
    new_prod_html = "".join(gen_product_card(p, cat_map) for p in new_products)
    bestseller_prod_html = "".join(gen_product_card(p, cat_map) for p in bestseller_products)

    index_data = {
        "header": header_rendered,
        "footer": footer_rendered,
        "carousel_html": carousel_html,
        "category_list": cat_list_html,
        "product_list": prod_item_html,
        "new_product_list": new_prod_html,
        "bestseller_list": bestseller_prod_html
    }
    index_html = render_template(tpl_index, index_data)
    index_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)
    all_sitemap_urls.append(f"{SITE_DOMAIN}/")

    # ===================== 2. 生成分类列表页 + 商品详情页 =====================
    for cat_name, cat_info in cat_map.items():
        cat_slug = cat_info["slug"]
        cat_desc = cat_info["desc"]
        cat_dir = os.path.join(OUTPUT_DIR, cat_slug)
        mkdir(cat_dir)

        # 当前分类下商品
        cat_prods = [p for p in prod_map if p["cat"] == cat_name]
        cat_prod_html = "".join(gen_product_card(p, cat_map) for p in cat_prods)

        # 生成分类列表页
        cat_page_data = {
            "header": header_rendered,
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

            # 商品多图处理
            images = [p["img"]]
            if p.get("images"):
                if isinstance(p["images"], list):
                    images = p["images"]
                elif isinstance(p["images"], str) and p["images"].strip():
                    images = [img.strip() for img in p["images"].split(",") if img.strip()]

            images_html = ""
            dots_html = ""
            thumbnails_html = ""
            for idx, img_url in enumerate(images):
                active = "active" if idx == 0 else ""
                images_html += f'<img src="{img_url}" alt="Product {idx+1}" class="carousel-img {active}">\n'
                dots_html += f'<span class="dot {active}" onclick="goToSlide({idx})"></span>\n'
                thumbnails_html += f'<div class="thumbnail {active}" onclick="changeImage({idx+1})"><img src="{img_url}" alt="Thumbnail {idx+1}"></div>\n'

            # 相关商品（同分类下其他商品 + 其他分类商品补充，最多15个）
            related = [rp for rp in cat_prods if rp["slug"] != prod_slug][:15]
            if len(related) < 15:
                other_prods = [rp for rp in prod_map if rp["cat"] != cat_name and rp["slug"] != prod_slug]
                related += other_prods[:15 - len(related)]
            related_html = "".join(gen_related_card(rp, cat_map) for rp in related)

            prod_page_data = {
                "header": header_rendered,
                "footer": footer_rendered,
                "product_title": p["title"],
                "product_img": p["img"],
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

    # ===================== 3. 生成自定义页面 =====================
    for slug, page_info in page_map.items():
        page_dir = os.path.join(OUTPUT_DIR, slug)
        mkdir(page_dir)
        page_data = {
            "header": header_rendered,
            "footer": footer_rendered,
            "page_title": page_info["title"],
            "page_content": page_info["content"]
        }
        page_html = render_template(tpl_custom, page_data)
        page_file = os.path.join(page_dir, "index.html")
        with open(page_file, "w", encoding="utf-8") as f:
            f.write(page_html)
        all_sitemap_urls.append(f"{SITE_DOMAIN}/{slug}/")

    # ===================== 4. 生成 robots.txt & sitemap.xml =====================
    gen_robots()
    gen_sitemap(all_sitemap_urls)
    print("✅ 全部页面、robots.txt、sitemap.xml 生成完成！")

if __name__ == "__main__":
    main()
