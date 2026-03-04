import html
import importlib
import json
import os
import re
import urllib.parse
from datetime import datetime
from typing import Dict, List, Union

import feedparser
import requests
import streamlit as st
import streamlit.components.v1 as components
from openai import AzureOpenAI

def try_load_dotenv() -> None:
	try:
		dotenv_module = importlib.import_module("dotenv")
		loader = getattr(dotenv_module, "load_dotenv", None)
		if callable(loader):
			loader()
	except Exception:
		pass


try_load_dotenv()


AZURE_REQUIRED_VARS = [
	"AZURE_OPENAI_ENDPOINT",
	"AZURE_OPENAI_API_KEY",
	"AZURE_OPENAI_DEPLOYMENT",
]

WHATSAPP_WEB_PREFILL_MAX_URL_LENGTH = 1800
PRIMARY_COLOR = "#005eac"

AZURE_ENV_ALIASES = {
	"AZURE_OPENAI_DEPLOYMENT": ["AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_DEPLOYMENT_NAME"],
}


TOPIC_QUERIES = {
	"Innovations": [
		"innovations life insurance latest news",
		"innovations general insurance latest news",
		"innovations fintech finance latest news",
		"innovations banking industry latest news",
	],
	"Artificial Intelligence": [
		"artificial intelligence life insurance latest news",
		"artificial intelligence general insurance latest news",
		"artificial intelligence fintech finance latest news",
		"artificial intelligence banking industry latest news",
	],
	"Generative AI": [
		"generative ai genai life insurance latest news",
		"generative ai genai general insurance latest news",
		"generative ai genai fintech finance latest news",
		"generative ai genai banking industry latest news",
	],
}

SECTION_ORDER = [
	"KNOWLEDGEBYTE",
	"Why Now? – The Shift",
	"Core Capabilities / Key Developments",
	"How It Works",
	"Challenges & Considerations",
	"Conclusion",
]

SECTION_DISPLAY_TITLES = {
	"KNOWLEDGEBYTE": "KNOWLEDGEBYTE – {result_title}",
	"Why Now? – The Shift": "🌐 Why Now? – The Shift",
	"Core Capabilities / Key Developments": "🚀 Core Capabilities / Key Developments",
	"How It Works": "⚙️ How It Works",
	"Challenges & Considerations": "⚠️ Challenges & Considerations",
	"Conclusion": "✅ Conclusion",
}

SECTION_ALIASES = {
	"KNOWLEDGEBYTE": ["knowledgebyte", "knowledge byte"],
	"Why Now? – The Shift": ["why now", "the shift"],
	"Core Capabilities / Key Developments": ["core capabilities", "key developments"],
	"How It Works": ["how it works"],
	"Challenges & Considerations": ["challenges", "considerations"],
	"Conclusion": ["conclusion"],
}


def strip_html(text: str) -> str:
	clean = re.sub(r"<[^>]+>", "", text or "")
	return html.unescape(clean).strip()


def extract_image_link(entry) -> str:
	for attr in ("media_content", "media_thumbnail"):
		media_items = entry.get(attr, [])
		if media_items and isinstance(media_items, list):
			first = media_items[0]
			if isinstance(first, dict) and first.get("url"):
				return first["url"]

	for link in entry.get("links", []):
		if isinstance(link, dict):
			link_type = (link.get("type") or "").lower()
			if link_type.startswith("image/") and link.get("href"):
				return link["href"]
	return ""


def get_env_with_aliases(var_name: str) -> str:
	alias_names = AZURE_ENV_ALIASES.get(var_name, [var_name])
	for alias in alias_names:
		value = (os.getenv(alias) or "").strip()
		if value:
			return value
	return ""


def canonicalize_heading(text: str) -> str:
	return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


@st.cache_data(ttl=3600)
def fetch_article_context(link: str) -> Dict[str, str]:
	if not link:
		return {"resolved_url": "", "article_excerpt": ""}

	try:
		response = requests.get(
			link,
			timeout=20,
			allow_redirects=True,
			headers={"User-Agent": "Mozilla/5.0 (NewsDigestBot/1.0)"},
		)
		response.raise_for_status()
		resolved_url = response.url or link
		content_type = (response.headers.get("Content-Type") or "").lower()
		if "text/html" not in content_type:
			return {"resolved_url": resolved_url, "article_excerpt": ""}

		html_text = response.text or ""
		html_text = re.sub(r"<script[^>]*>.*?</script>", " ", html_text, flags=re.DOTALL | re.IGNORECASE)
		html_text = re.sub(r"<style[^>]*>.*?</style>", " ", html_text, flags=re.DOTALL | re.IGNORECASE)
		html_text = re.sub(r"<noscript[^>]*>.*?</noscript>", " ", html_text, flags=re.DOTALL | re.IGNORECASE)
		paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html_text, flags=re.DOTALL | re.IGNORECASE)

		clean_paragraphs = []
		for paragraph in paragraphs:
			clean = re.sub(r"\s+", " ", strip_html(paragraph)).strip()
			if len(clean.split()) >= 8:
				clean_paragraphs.append(clean)

		excerpt = " ".join(clean_paragraphs[:12]).strip()
		if len(excerpt) > 4500:
			excerpt = excerpt[:4500].rsplit(" ", 1)[0]

		return {"resolved_url": resolved_url, "article_excerpt": excerpt}
	except Exception:
		return {"resolved_url": link, "article_excerpt": ""}


@st.cache_data(ttl=1800)
def fetch_topic_updates(query: Union[str, List[str]], max_items: int = 10) -> List[Dict[str, str]]:
	query_sequence = query if isinstance(query, list) else [query]

	for base_query in query_sequence:
		query_candidates = [f"{base_query} when:7d", f"{base_query} when:30d", base_query]

		for rss_query in query_candidates:
			rss_url = (
				"https://news.google.com/rss/search?"
				f"q={urllib.parse.quote_plus(rss_query)}&hl=en-IN&gl=IN&ceid=IN:en"
			)
			response = requests.get(
				rss_url,
				timeout=20,
				headers={"User-Agent": "Mozilla/5.0 (NewsDigestBot/1.0)"},
			)
			response.raise_for_status()
			feed = feedparser.parse(response.content)

			updates: List[Dict[str, str]] = []
			for entry in feed.entries[:max_items]:
				updates.append(
					{
						"title": strip_html(entry.get("title", "Untitled")),
						"link": entry.get("link", ""),
						"source": strip_html(entry.get("source", {}).get("title", "")),
						"published": strip_html(entry.get("published", "")),
						"summary": strip_html(entry.get("summary", "")),
						"image": extract_image_link(entry),
					}
				)

			if updates:
				return updates

	return []


def build_context_for_llm(result_title: str, selected_update: Dict[str, str]) -> str:
	link = (selected_update.get("link") or "").strip()
	source = (selected_update.get("source") or "").strip()
	published = (selected_update.get("published") or "").strip()
	summary = (selected_update.get("summary") or "").strip()
	article_context = fetch_article_context(link)
	resolved_url = (article_context.get("resolved_url") or "").strip()
	article_excerpt = (article_context.get("article_excerpt") or "").strip()
	lines = [
		f"Selected Topic (specific result): {result_title}",
		f"Source: {source or 'Unknown'}",
		f"Published: {published or 'Unknown'}",
		f"Summary from feed: {summary or 'Not available'}",
		f"Resolved source URL (after redirects): {resolved_url or 'Not available'}",
		"Extracted article text snippet (may be empty if page blocks scraping):",
		article_excerpt or "Not available",
		"Use only this source link as material:",
		f"Link: {link or 'No link available'}",
		"Generate an in-depth explanation only for this selected result.",
		"Do not use any information from any other result or source.",
	]
	return "\n".join(lines)


def generate_with_azure_openai(result_title: str, selected_update: Dict[str, str]) -> str:
	endpoint = get_env_with_aliases("AZURE_OPENAI_ENDPOINT")
	api_key = get_env_with_aliases("AZURE_OPENAI_API_KEY")
	deployment = get_env_with_aliases("AZURE_OPENAI_DEPLOYMENT")
	api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")

	if not endpoint or not api_key or not deployment:
		raise ValueError(
			"Azure OpenAI configuration missing. Set AZURE_OPENAI_ENDPOINT, "
			"AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT."
		)

	client = AzureOpenAI(
		azure_endpoint=endpoint,
		api_key=api_key,
		api_version=api_version,
	)

	system_prompt = (
		"You are an expert technology analyst and editorial writer. Produce a detailed weekly "
		"digest in WhatsApp-friendly formatting using only the provided selected-result context. "
		"Output MUST be in exactly 6 sections, each wrapped with delimiters in this format: "
		"<<SECTION:SECTION_TITLE>> followed by section text. "
		"Use these exact section titles in this exact order: "
		"1) KNOWLEDGEBYTE "
		"2) Why Now? – The Shift "
		"3) Core Capabilities / Key Developments "
		"4) How It Works "
		"5) Challenges & Considerations "
		"6) Conclusion. "
		"Write richly detailed content (total target 1000-1400 words). "
		"Formatting requirements for WhatsApp compatibility: "
		"- Use *bold* for key phrases. "
		"- Use hyphen bullets only, like '- *Heading* : explanation'. "
		"- Keep short paragraphs where needed, but ensure most content is in bullet points. "
		"- Use at most one emoji per section, and emojis are optional. "
		"In KNOWLEDGEBYTE, include a 2-3 paragraph narrative intro before bullets. "
		"Keep tone professional, engaging, and practical for business readers. "
		"Do not leave any section blank. Every section must contain at least 6 substantive bullets, each with concrete explanation. "
		"Each section must discuss a different angle, not repeated metadata. "
		"Avoid generic one-line bullets; explain implications, mechanisms, and practical takeaways. "
		"Use available context to infer implications, workflows, risks, and opportunities; "
		"do not fabricate specific numbers, names, quotes, or unverifiable claims. "
		"Do not include any content outside these delimiters. "
		"If source evidence is thin, explicitly keep statements high-level and analytical."
	)

	user_prompt = build_context_for_llm(result_title, selected_update)

	response = client.chat.completions.create(
		model=deployment,
		messages=[
			{"role": "system", "content": system_prompt},
			{"role": "user", "content": user_prompt},
		],
		temperature=0.3,
		max_tokens=2200,
	)

	return response.choices[0].message.content.strip()


def fallback_digest(result_title: str, selected_update: Dict[str, str]) -> str:
	if not selected_update:
		return "\n\n".join([f"<<SECTION:{title}>>" for title in SECTION_ORDER])

	blocks = []
	for title in SECTION_ORDER:
		section_body = build_dynamic_section_fallback(title, result_title, selected_update)
		blocks.append(f"<<SECTION:{title}>>\n{section_body}")
	return "\n\n".join(blocks)


def has_sufficient_section_content(sections: List[Dict[str, str]]) -> bool:
	if len(sections) < len(SECTION_ORDER):
		return False
	rich_sections = sum(
		1 for section in sections if len((section.get("content") or "").strip().split()) >= 20
	)
	return rich_sections >= 4


def build_dynamic_section_fallback(
	section_title: str, result_title: str, selected_update: Dict[str, str]
) -> str:
	source = selected_update.get("source", "Unknown")
	published = selected_update.get("published", "Unknown")
	summary = selected_update.get("summary", "")

	if section_title == "KNOWLEDGEBYTE":
		return "\n".join(
			[
				f"In this week’s KnowledgeByte, we explore *{result_title}* and what it signals for policy and operations.",
				"This update points to growing momentum in applying AI methods to improve risk visibility, early warning readiness, and decision support across disaster management lifecycles.",
				"The broader significance is not only technical adoption, but also institutional readiness: organizations are increasingly expected to move from static risk reports toward living, continuously updated intelligence pipelines.",
				"As a result, AI in disaster risk reduction should be viewed as an operational capability that reshapes planning cycles, inter-agency coordination, and on-ground response timing.",
				"- *What this means for leaders* : AI initiatives in DRR need clear outcomes, such as earlier warning lead time, faster triage, and improved resource allocation quality.",
				"- *Why this matters now* : climate-linked uncertainty and dense data environments create conditions where manual-only monitoring is too slow for high-stakes decisions.",
				f"Source context: {source} • {published}",
				f"Known summary: {summary or 'Limited feed details are available, so this brief focuses on practical interpretation and implications.'}",
			]
		)

	if section_title == "Why Now? – The Shift":
		return "\n".join(
			[
				"- *Escalating hazard volatility* : Frequency and complexity of extreme events raise the value of near-real-time risk interpretation.",
				"- *Data growth beyond manual capacity* : Satellite, sensor, and field-report streams now require machine-supported triage to extract actionable signals quickly.",
				"- *Pressure for measurable resilience outcomes* : Public agencies and NGOs are expected to demonstrate impact, not just activity, in preparedness programs.",
				"- *Decision velocity as a competitive advantage* : Earlier interventions often lower total response cost and reduce downstream disruption.",
				"- *Shift from reactive to anticipatory operations* : AI enables planning decisions before an event peaks, not only after damage is visible.",
				"- *Organizational modernization driver* : DRR teams are aligning data, process, and governance to support repeatable, evidence-based actions.",
			]
		)

	if section_title == "Core Capabilities / Key Developments":
		return "\n".join(
			[
				"- *Predictive risk modeling* : Supports hotspot identification and scenario planning before conditions deteriorate.",
				"- *Multi-source data fusion* : Integrates weather feeds, geospatial context, and historical incident patterns for stronger situational awareness.",
				"- *Early warning intelligence* : Improves alert relevance by linking predicted impact with vulnerable locations and population exposure.",
				"- *Operational prioritization* : Helps rank interventions such as evacuation support, logistics staging, and frontline staffing.",
				"- *Decision-support dashboards* : Converts technical model output into readable, role-specific views for planners and responders.",
				"- *Continuous learning loops* : Improves reliability by feeding post-event observations back into future model calibration.",
			]
		)

	if section_title == "How It Works":
		return "\n".join(
			[
				"- *Step 1: Data ingestion* : Gather hazard forecasts, terrain and infrastructure layers, and field observations into a unified pipeline.",
				"- *Step 2: Signal extraction* : Use AI models to detect pattern shifts, anomaly clusters, and likely impact corridors.",
				"- *Step 3: Exposure estimation* : Map event likelihood against population, assets, and service dependencies.",
				"- *Step 4: Operational translation* : Convert analytics into triggers, action queues, and escalation pathways.",
				"- *Step 5: Human review and governance* : Validate recommendations with domain experts before critical decisions.",
				"- *Step 6: Feedback and retraining* : Capture event outcomes to improve model quality, thresholds, and playbooks over time.",
			]
		)

	if section_title == "Challenges & Considerations":
		return "\n".join(
			[
				"- *Data quality limitations* : Sparse or noisy inputs can bias predictions, especially in underserved geographies.",
				"- *Governance and privacy requirements* : Location-linked and population data demand strict access control, retention, and accountability.",
				"- *Interpretability expectations* : Emergency leaders need transparent rationale before acting on model-driven recommendations.",
				"- *Integration complexity* : New AI systems must align with legacy tools, SOPs, and cross-agency protocols.",
				"- *Capability and training gaps* : Teams require operational fluency in both analytics interpretation and incident command processes.",
				"- *False confidence risk* : Overreliance on automated outputs without human context can lead to poor decisions under uncertainty.",
			]
		)

	return "\n".join(
		[
			"*Conclusion: AI as an enabler for resilience*",
			"- *Strategic takeaway* : AI for disaster risk reduction delivers value when it is embedded in governance, operations, and accountability frameworks.",
			"- *Execution priority* : Organizations should pair forecasting systems with clear trigger logic, role ownership, and response playbooks.",
			"- *Risk management principle* : Treat model outputs as decision support, not autonomous command, especially in high-uncertainty situations.",
			"- *Scaling path* : Start with focused use cases, prove measurable outcomes, then expand across geographies and hazard types.",
			"- *Long-term implication* : The shift is from reactive incident handling to proactive resilience engineering powered by continuous intelligence.",
			"- *Context note* : This brief is based on available source context and practical interpretation where direct detail is limited.",
		]
	)


def parse_sections_from_headings(digest: str) -> Dict[str, str]:
	lines = digest.splitlines()
	line_starts = []
	offset = 0
	for line in lines:
		line_starts.append(offset)
		offset += len(line) + 1

	heading_hits: Dict[str, int] = {}
	for idx, line in enumerate(lines):
		line_key = canonicalize_heading(line)
		if not line_key or len(line_key) > 80:
			continue
		for section_title, aliases in SECTION_ALIASES.items():
			if section_title in heading_hits:
				continue
			for alias in aliases:
				if canonicalize_heading(alias) and canonicalize_heading(alias) in line_key:
					heading_hits[section_title] = line_starts[idx]
					break

	if len(heading_hits) < 2:
		return {}

	ordered_hits = sorted(heading_hits.items(), key=lambda item: item[1])
	content_by_title: Dict[str, str] = {}
	for idx, (title, start) in enumerate(ordered_hits):
		end = ordered_hits[idx + 1][1] if idx + 1 < len(ordered_hits) else len(digest)
		chunk = digest[start:end].strip()
		if chunk:
			content_by_title[title] = chunk

	return content_by_title


def parse_sectioned_digest(digest: str) -> List[Dict[str, str]]:
	pattern = r"<<SECTION:(.*?)>>"
	matches = list(re.finditer(pattern, digest, flags=re.DOTALL))
	content_by_title: Dict[str, str] = {}

	if not matches:
		content_by_title = parse_sections_from_headings(digest)
		if not content_by_title:
			return [{"title": title, "content": digest.strip() if title == "KNOWLEDGEBYTE" else ""} for title in SECTION_ORDER]
		return [{"title": title, "content": content_by_title.get(title, "").strip()} for title in SECTION_ORDER]

	for idx, match in enumerate(matches):
		title = match.group(1).strip()
		start = match.end()
		end = matches[idx + 1].start() if idx + 1 < len(matches) else len(digest)
		content = digest[start:end].strip()
		if content and title in SECTION_ORDER:
			content_by_title[title] = content

	sections: List[Dict[str, str]] = []
	for title in SECTION_ORDER:
		sections.append({"title": title, "content": content_by_title.get(title, "")})

	return sections


def build_section_messages(
	result_title: str,
	sections: List[Dict[str, str]],
	selected_update: Dict[str, str],
	section_images: Dict[str, str],
) -> List[Dict[str, str]]:
	messages: List[Dict[str, str]] = []
	for section in sections:
		title = section["title"]
		content = section["content"]
		if not content.strip():
			content = build_dynamic_section_fallback(title, result_title, selected_update)
		image_url = (section_images.get(title) or "").strip()
		display_title = SECTION_DISPLAY_TITLES.get(title, title).format(result_title=result_title)
		header = f"*{display_title}*"
		text = f"{header}\n\n{content}"
		if image_url:
			text = f"{image_url}\n\n{text}"

		messages.append({"title": display_title, "text": text, "image_url": image_url})

	links_block = ["*Links:*"]
	if selected_update.get("link"):
		links_block.append(selected_update["link"])
	if selected_update.get("image"):
		links_block.append(selected_update["image"])
	links_block.append(f"Generated on: {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
	messages.append({"title": "Links", "text": "\n\n".join(links_block), "image_url": ""})

	return messages


def render_copy_button(text_to_copy: str, key: str) -> None:
	payload = json.dumps(text_to_copy)
	status_id = f"copy_status_{key}"
	components.html(
		f"""
		<div style="margin: 6px 0;">
		  <button
			onclick='navigator.clipboard.writeText({payload}).then(() => {{
			  document.getElementById("{status_id}").innerText = "Copied ✅";
			}})'
			style="padding:8px 14px;border-radius:8px;border:1px solid #7fb5e5;background:#eaf3ff;color:#0f172a;font-weight:600;cursor:pointer;"
		  >Copy WhatsApp Text</button>
		  <span id="{status_id}" style="margin-left:10px;color:green;font-weight:600;"></span>
		</div>
		""",
		height=60,
	)


def clean_phone_number(raw: str) -> str:
	return re.sub(r"\D", "", raw or "")


def build_whatsapp_url(phone: str, message: str) -> Dict[str, str]:
	clean_phone = clean_phone_number(phone)
	query_prefix = f"phone={clean_phone}&" if clean_phone else ""
	base_web_url = f"https://web.whatsapp.com/send?{query_prefix}"
	base_app_url = f"whatsapp://send?{query_prefix}"
	encoded_message = urllib.parse.quote(message)
	prefill_web_url = f"{base_web_url}text={encoded_message}"
	prefill_app_url = f"{base_app_url}text={encoded_message}"

	return {
		"web_prefill_url": prefill_web_url,
		"web_chat_url": base_web_url,
		"app_prefill_url": prefill_app_url,
		"app_chat_url": base_app_url,
		"web_prefill_ok": len(prefill_web_url) <= WHATSAPP_WEB_PREFILL_MAX_URL_LENGTH,
	}


def get_missing_azure_vars() -> List[str]:
	missing = []
	for var_name in AZURE_REQUIRED_VARS:
		if not get_env_with_aliases(var_name):
			missing.append(var_name)
	return missing


def format_update_option(update: Dict[str, str]) -> str:
	title = (update.get("title") or "Untitled").strip()
	if len(title) > 88:
		title = f"{title[:85].rstrip()}…"
	source = (update.get("source") or "Unknown source").strip()
	published = (update.get("published") or "Unknown date").strip()
	return f"{title}  |  {source}  |  {published}"


def apply_custom_light_theme() -> None:
	st.markdown(
		f"""
		<style>
		:root {{
			--kb-primary: {PRIMARY_COLOR};
			--kb-bg: #f4f8fc;
			--kb-surface: #ffffff;
			--kb-border: #d6e3f3;
			--kb-text: #0f172a;
			--kb-muted: #334155;
			--kb-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
		}}

		.main .block-container {{
			max-width: 980px;
			padding-top: 1.15rem;
			padding-bottom: 1.6rem;
		}}

		html, body, [class*="css"]  {{
			background: var(--kb-bg) !important;
			color: var(--kb-text) !important;
		}}

		.stApp {{
			background: linear-gradient(180deg, #f7fbff 0%, var(--kb-bg) 55%, #eef5fd 100%) !important;
		}}

		h1, h2, h3, .stMarkdown p strong {{
			color: var(--kb-primary) !important;
		}}

		p, span, label, li,
		.stMarkdown, .stMarkdown p, .stMarkdown li,
		div[data-testid="stWidgetLabel"],
		div[data-baseweb="select"] *,
		div[role="radiogroup"] label,
		input, textarea {{
			color: var(--kb-text) !important;
		}}

		a {{
			color: var(--kb-primary) !important;
		}}

		[data-testid="stHeader"] {{
			background: rgba(255,255,255,0.96) !important;
			border-bottom: 1px solid var(--kb-border) !important;
		}}

		[data-testid="stSidebar"] {{
			background: #f2f8ff !important;
			border-right: 1px solid var(--kb-border) !important;
		}}

		[data-testid="stMetricValue"], .stCaption {{
			color: var(--kb-muted) !important;
		}}

		div[data-testid="stTextInput"] input,
		div[data-testid="stTextArea"] textarea,
		div[data-testid="stSelectbox"] div[data-baseweb="select"],
		div[role="radiogroup"] {{
			background: var(--kb-surface) !important;
			border: 1px solid var(--kb-border) !important;
			border-radius: 12px !important;
			box-shadow: var(--kb-shadow);
		}}

		div[role="radiogroup"] {{
			padding: 0.4rem 0.65rem;
			gap: 0.35rem;
		}}

		h1 {{
			font-size: 1.95rem !important;
			margin-bottom: 0.15rem !important;
		}}

		h2, h3 {{
			margin-top: 0.65rem !important;
		}}

		/* Selectbox closed control (value shown before opening dropdown) */
		div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
		div[data-testid="stSelectbox"] div[data-baseweb="select"] > div > div,
		div[data-testid="stSelectbox"] div[data-baseweb="select"] input,
		div[data-testid="stSelectbox"] div[data-baseweb="select"] span {{
			background: #ffffff !important;
			color: #000000 !important;
			-webkit-text-fill-color: #000000 !important;
		}}

		div[data-testid="stSelectbox"] div[data-baseweb="select"] input::placeholder,
		div[data-testid="stSelectbox"] div[data-baseweb="select"] div[aria-hidden="true"] {{
			color: #000000 !important;
			-webkit-text-fill-color: #000000 !important;
		}}

		/* BaseWeb select dropdown popup (portal) */
		div[role="listbox"],
		ul[role="listbox"],
		div[data-baseweb="menu"],
		div[data-baseweb="popover"] {{
			background: var(--kb-surface) !important;
			color: var(--kb-text) !important;
			border: 1px solid var(--kb-border) !important;
		}}

		li[role="option"],
		div[role="option"],
		div[data-baseweb="menu"] div {{
			background: var(--kb-surface) !important;
			color: var(--kb-text) !important;
		}}

		li[role="option"]:hover,
		div[role="option"]:hover,
		li[role="option"][aria-selected="true"],
		div[role="option"][aria-selected="true"] {{
			background: #eaf3ff !important;
			color: var(--kb-text) !important;
		}}

		div[data-testid="stTextArea"] textarea:disabled {{
			color: var(--kb-text) !important;
			-webkit-text-fill-color: var(--kb-text) !important;
			opacity: 1 !important;
		}}

		div[data-testid="stTextInput"] input:focus,
		div[data-testid="stTextArea"] textarea:focus {{
			border-color: var(--kb-primary) !important;
			box-shadow: 0 0 0 1px var(--kb-primary) !important;
		}}

		.stButton > button,
		a[data-testid="stLinkButton"] {{
			background: #eaf3ff !important;
			color: var(--kb-text) !important;
			border: 1px solid #7fb5e5 !important;
			border-radius: 12px !important;
			font-weight: 600 !important;
			min-height: 2.55rem;
		}}

		.stButton > button *,
		a[data-testid="stLinkButton"],
		a[data-testid="stLinkButton"] * {{
			color: var(--kb-text) !important;
			-webkit-text-fill-color: var(--kb-text) !important;
		}}

		.stButton > button:hover,
		a[data-testid="stLinkButton"]:hover {{
			background: #dbeeff !important;
			border-color: #5d9cd4 !important;
		}}

		[data-testid="stAlert"] {{
			border-radius: 10px !important;
			border: 1px solid var(--kb-border) !important;
		}}

		div[data-testid="stExpander"] > details {{
			background: var(--kb-surface) !important;
			border: 1px solid var(--kb-border) !important;
			border-radius: 12px !important;
			box-shadow: var(--kb-shadow);
		}}

		@media (max-width: 768px) {{
			.main .block-container {{
				padding-top: 0.7rem;
				padding-left: 0.7rem;
				padding-right: 0.7rem;
				padding-bottom: 1rem;
			}}

			h1 {{
				font-size: 1.55rem !important;
			}}

			.stButton > button,
			a[data-testid="stLinkButton"] {{
				width: 100% !important;
			}}

			div[data-testid="stTextArea"] textarea {{
				font-size: 0.95rem !important;
			}}
		}}
		</style>
		""",
		unsafe_allow_html=True,
	)


def main() -> None:
	st.set_page_config(page_title="KnowledgeByte Generator", page_icon="🧠", layout="wide")
	apply_custom_light_theme()
	st.title("🧠 KnowledgeByte Generator")
	st.caption(
		"✨ Fetches latest web updates, generates a comprehensive AI brief, and formats it for WhatsApp sharing."
	)

	missing_azure_vars = get_missing_azure_vars()
	azure_ok = len(missing_azure_vars) == 0
	if azure_ok:
		st.success("Azure OpenAI: Configured")
	else:
		st.warning(
			"Azure OpenAI: Missing env vars (fallback mode available) -> "
			+ ", ".join(missing_azure_vars)
		)

	if "selected_digest" not in st.session_state:
		st.session_state["selected_digest"] = ""
	if "selected_digest_topic" not in st.session_state:
		st.session_state["selected_digest_topic"] = ""
	if "selected_digest_link" not in st.session_state:
		st.session_state["selected_digest_link"] = ""
	if "section_images" not in st.session_state:
		st.session_state["section_images"] = {}
	if "last_generation_mode" not in st.session_state:
		st.session_state["last_generation_mode"] = ""
	if "last_generation_error" not in st.session_state:
		st.session_state["last_generation_error"] = ""

	selected_topic = st.selectbox(
		"📚 Choose a topic (AI generates details only for this topic)",
		list(TOPIC_QUERIES.keys()),
	)
	refresh = st.button("🔄 Refresh Latest Updates", use_container_width=True)

	if refresh:
		fetch_topic_updates.clear()

	with st.spinner("Searching the web for latest updates..."):
		try:
			updates = fetch_topic_updates(TOPIC_QUERIES[selected_topic], max_items=12)
		except Exception as ex:
			st.error(f"Failed to fetch updates: {ex}")
			updates = []

	selected_result = None
	st.subheader("🗞️ Latest Web Results (Past 7 Days)")
	if not updates:
		st.info("No updates found right now. Try refresh in a minute.")
	else:
		display_count = min(len(updates), 8)
		result_idx = st.selectbox(
			"🎯 Select one result from latest updates",
			options=list(range(display_count)),
			format_func=lambda idx: format_update_option(updates[idx]),
		)
		selected_result = updates[result_idx]
		if selected_result.get("link"):
			st.markdown(f"Selected link: [Open source]({selected_result['link']})")
		if selected_result.get("summary"):
			st.caption(selected_result.get("summary", ""))

	generate = st.button("⚡ Generate Comprehensive Weekly Brief", use_container_width=True)
	if generate:
		if not selected_result:
			st.warning("Please select one specific result first.")
			return
		mode = "ai"
		error_message = ""
		with st.spinner("Creating GenAI digest..."):
			try:
				digest = generate_with_azure_openai(selected_result["title"], selected_result)
				sections_check = parse_sectioned_digest(digest)
				if not has_sufficient_section_content(sections_check):
					digest = generate_with_azure_openai(selected_result["title"], selected_result)
					sections_check = parse_sectioned_digest(digest)
					if not has_sufficient_section_content(sections_check):
						mode = "fallback"
						error_message = (
							"AI response did not contain sufficiently detailed section content after retry."
						)
						digest = fallback_digest(selected_result["title"], selected_result)
			except Exception as ex:
				mode = "fallback"
				error_message = str(ex)
				digest = fallback_digest(selected_result["title"], selected_result)

		st.session_state["last_generation_mode"] = mode
		st.session_state["last_generation_error"] = error_message
		if mode == "fallback":
			st.error(
				"AI generation failed; fallback content was used. "
				f"Reason: {error_message or 'Unknown error'}"
			)
		else:
			st.success("AI-generated content created successfully.")

		st.session_state["selected_digest"] = digest
		st.session_state["selected_digest_topic"] = selected_result["title"]
		st.session_state["selected_digest_link"] = selected_result.get("link", "")

	digest_text = st.session_state.get("selected_digest", "")
	digest_topic = st.session_state.get("selected_digest_topic", "")
	digest_link = st.session_state.get("selected_digest_link", "")
	if digest_text and selected_result and digest_topic == selected_result.get("title", ""):
		if st.session_state.get("last_generation_mode") == "fallback":
			st.caption("Current output source: fallback template")
		elif st.session_state.get("last_generation_mode") == "ai":
			st.caption("Current output source: Azure OpenAI")

		sections = parse_sectioned_digest(digest_text)

		st.subheader("📘 Comprehensive Response")
		with st.expander("View full generated response", expanded=False):
			st.write(digest_text)

		st.subheader("💬 Section-wise WhatsApp Messages")
		st.caption("Each section is a separate message. You can add an image link at the top of each section.")
		st.session_state["wa_phone"] = st.text_input(
			"📱 WhatsApp Number (optional, with country code, e.g., 91XXXXXXXXXX)",
			value=st.session_state.get("wa_phone", ""),
		)
		send_via = st.radio(
			"🚀 Send copied text via",
			options=["WhatsApp App", "WhatsApp Web", "Both"],
			index=0,
			horizontal=False,
			key="wa_send_via",
		)
		phone = clean_phone_number(st.session_state["wa_phone"])

		section_images = {}
		default_image = selected_result.get("image", "")
		with st.expander("🖼️ Section image links (optional)", expanded=False):
			for title in SECTION_ORDER:
				current_value = st.session_state["section_images"].get(title, default_image)
				section_images[title] = st.text_input(
					f"Image URL for section: {SECTION_DISPLAY_TITLES.get(title, title).format(result_title=selected_result['title'])}",
					value=current_value,
					key=f"img_{title}",
				)

		st.session_state["section_images"] = section_images
		section_messages = build_section_messages(
			selected_result["title"],
			sections,
			selected_result,
			section_images,
		)

		for idx, section_message in enumerate(section_messages, start=1):
			title = section_message["title"]
			message = section_message["text"]
			image_url = (section_message.get("image_url") or "").strip()
			with st.expander(f"Message {idx}: {title}", expanded=(idx == 1)):
				if image_url:
					st.image(image_url, caption="Embedded image preview", use_container_width=True)
				st.text_area(
					f"Preview Box {idx} (Locked)",
					value=message,
					height=180,
					key=f"preview_{idx}_{title}",
					disabled=True,
				)
				render_copy_button(message, key=f"{idx}_{title}")

				wa_section = build_whatsapp_url(st.session_state.get("wa_phone", ""), message)
				if send_via in ["WhatsApp App", "Both"]:
					st.link_button(f"Open Message {idx} in WhatsApp App", wa_section["app_prefill_url"])

				if send_via in ["WhatsApp Web", "Both"]:
					if wa_section["web_prefill_ok"]:
						st.link_button(f"Open Message {idx} in WhatsApp Web", wa_section["web_prefill_url"])
					else:
						st.caption(
							"Message is too long for WhatsApp Web prefill URL. Open Web chat and paste copied text."
						)
						st.link_button(f"Open Chat {idx} in WhatsApp Web", wa_section["web_chat_url"])

		combined_messages = "\n\n------------------\n\n".join(
			[msg["text"] for msg in section_messages]
		)
		st.subheader("🧾 Combined Message (Optional)")
		st.text_area("Combined Preview", value=combined_messages, height=260)
		render_copy_button(combined_messages, key="combined")
		combined_wa = build_whatsapp_url(phone, combined_messages)

		if send_via in ["WhatsApp App", "Both"]:
			st.link_button("Open Combined in WhatsApp App", combined_wa["app_prefill_url"])

		if send_via in ["WhatsApp Web", "Both"]:
			if combined_wa["web_prefill_ok"]:
				st.link_button("Open Combined in WhatsApp Web", combined_wa["web_prefill_url"])
			else:
				st.caption(
					"Combined text is too long for WhatsApp Web prefill URL. Open Web chat and paste copied text."
				)
				st.link_button("Open Chat in WhatsApp Web", combined_wa["web_chat_url"])


if __name__ == "__main__":
	main()
