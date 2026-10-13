"""Generate the two main architecture review options from identical geometry."""
from pathlib import Path
from html import escape
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).parent

def build(variant, paper, ink, muted, accent, tint):
    slug = f'main-{variant}'
    def text(x, y, value, cls='body'):
        return f'<text x="{x}" y="{y}" class="{cls}">{escape(value)}</text>'
    def label(x, y, value, width):
        return f'<rect x="{x}" y="{y}" width="{width}" height="20" fill="{paper}"/>' + text(x+8,y+16,value,'label')
    def icon(name,x,y):
        source = ET.fromstring((ROOT/'icons'/f'{name}.svg').read_text(encoding='utf-8'))
        _, _, width, height = map(float,source.attrib['viewBox'].split())
        for element in source.iter():
            element.tag = element.tag.split('}')[-1]
            for key,value in element.attrib.items():
                if key.startswith('on') or key in ('href','src'):
                    raise ValueError('Unexpected active or external icon content')
        content = ''.join(ET.tostring(child,encoding='unicode') for child in source)
        for identifier in re.findall(r'\bid="([^"]+)"',content):
            unique = f'{slug}-{name}-{x}-{y}-{identifier}'
            content = content.replace(f'id="{identifier}"',f'id="{unique}"').replace(f'url(#{identifier})',f'url(#{unique})')
        return f'<g aria-hidden="true" transform="translate({x} {y}) scale({24/width} {24/height})">{content}</g>'
    def node(x,y,name,tag,lines,kind='service'):
        fill = tint if kind=='focal' else ('#e2e5e6' if kind=='store' else '#ffffff')
        stroke = accent if kind=='focal' else ink
        s = f'<g><rect x="{x}" y="{y}" width="200" height="120" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>'
        technology = {'SQL Server fleet':'sqlserver','Collector':'python','Prometheus':'prometheus','Grafana':'grafana','MCP server':'python','Internal AI agent':'python','Streamlit chat':'streamlit'}.get(name)
        if technology:
            s += icon(technology,x+16,y+8)
        s += text(x+(48 if technology else 16),y+24,tag,'tag') + text(x+16,y+52,name,'name')
        for i,line in enumerate(lines): s += text(x+16,y+76+i*20,line)
        return s+'</g>'
    def arrow(d):
        return f'<path d="{d}" fill="none" stroke="{muted}" stroke-width="1.2" marker-end="url(#{slug}-arrow)"/>'
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 800" role="img" aria-labelledby="{slug}-title {slug}-desc"><title id="{slug}-title">Data Eyes — main architecture</title><desc id="{slug}-desc">Only the collector queries SQL Server. Grafana and MCP read Prometheus; the agent calls MCP monitoring tools. The Nginx gateway routes browser requests to Grafana and authenticated Streamlit chat, which calls the agent. External AI clients call MCP directly. Arrows point from caller to queried service.</desc><defs>'
    for suffix,color in [('arrow',muted),('arrow-accent',accent),('arrow-link','#2e5aa8')]:
        svg += f'<marker id="{slug}-{suffix}" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="{color}"/></marker>'
    svg += f'</defs><rect width="1600" height="800" fill="{paper}"/>'
    svg += text(40,48,'DATA EYES / SYSTEM OVERVIEW','eyebrow')
    svg += text(40,100,'One fleet. Continuous visibility.','title')
    svg += text(40,132,'One collector supplies the measurements used by dashboards and AI-assisted investigation.','subtitle')
    svg += f'<rect x="320" y="164" width="920" height="212" rx="8" fill="none" stroke="{muted}" stroke-opacity="0.25"/>'
    svg += text(344,192,'MONITOR / CONTINUOUS MONITORING','tag')
    svg += text(360,424,'MCP / MONITORING ACCESS','tag') + text(660,424,'AGENT / ASK THE FLEET','tag')
    for d in ['M360 280 H240','M660 280 H560','M960 280 H860',
              'M660 520 H560',
              'M560 480 H600 Q608 480 608 472 V400 Q608 392 616 392 H692 Q700 392 700 384 V340',
              'M240 540 H360', 'M960 520 H860', 'M1320 280 H1160',
              'M1420 340 V512 Q1420 520 1412 520 H1160']:
        svg += arrow(d)
    for args in [(248,252,'SQL',72),(568,252,'SCRAPE',84),(872,252,'PROMQL',80),
                 (572,492,'MCP',64),
                 (616,436,'PROMQL',88),(256,512,'MCP',64),(872,492,'HTTP',72),
                 (1176,252,'UI + SESSION',128),(1192,492,'/assistant/',128)]: svg += label(*args)
    svg += node(40,220,'SQL Server fleet','EXTERNAL SYSTEM',['Development · staging','Production'],'store')
    svg += node(360,220,'Collector','PYTHON / FASTAPI',['Scheduled read-only SQL','56 health checks'])
    svg += node(660,220,'Prometheus','METRIC STORE',['Scrape every 30 seconds','Retain 30 days'],'store')
    svg += node(960,220,'Grafana','DASHBOARDS + ALERTS',['Fleet and instance views','Email through SMTP'],'focal')
    svg += node(360,460,'MCP server','READ-ONLY TOOL API',['9 monitoring tools','Scoped collected metrics'],'focal')
    svg += node(660,460,'Internal AI agent','MODEL + TOOL LOOP',['Calls MCP tools directly','Provider keys stay here'])
    svg += node(40,460,'AI clients','EXTERNAL CLIENTS',['Claude Code and others','Authenticated MCP access'])
    svg += node(960,460,'Streamlit chat','INTERNAL / :8501',['Embedded in Grafana','Streamed answers'])
    svg += node(1320,220,'Nginx gateway','BROWSER ENTRY / :3000',['Grafana session for chat','HTTP + WebSocket proxy'])
    svg += text(1320,192,'BROWSER ACCESS','tag')
    svg += text(40,632,'COLLECTOR CONFIG','tag') + text(40,660,'instances.yaml','name')
    svg += text(40,684,'SQL fleet + connection strings; collector only.')
    svg += text(560,632,'MCP ACCESS POLICY','tag') + text(560,660,'mcp-access.yaml','name')
    svg += text(560,684,'Instance metadata, grants and token hashes; MCP only.')
    svg += text(1120,632,'SERVICE SETTINGS','tag') + text(1120,660,'.env','name')
    svg += text(1120,684,'Grafana settings, provider keys and agent MCP token.')
    svg += f'<line x1="40" y1="736" x2="1560" y2="736" stroke="{muted}" stroke-opacity="0.25"/>'
    svg += arrow('M40 764 H80') + text(96,768,'Caller → queried service','body')
    svg += text(480,768,'Only the collector connects to SQL Server.','body')
    svg += text(1120,768,'Docker Compose / runtime architecture','body') + '</svg>'
    name = '01 / Data Eyes · charcoal & silver' if variant=='brand' else '02 / Skill default · orange accent'
    receipt = ('Palette adapted from assets/logo.png: charcoal #20262a, silver #c4cccf. Neutral focal treatment intentionally preserves the monochrome logo.' if variant=='brand' else 'Shipped palette: paper #f5f5f5, ink #2d3142, accent #eb6c36.')
    html = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Data Eyes architecture — {variant}</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&amp;family=Geist:wght@400;500;600&amp;family=Geist+Mono:wght@400;500;600&amp;display=swap" rel="stylesheet">
<style>
* {{box-sizing:border-box}} body {{margin:0;padding:32px;background:{paper};color:{ink};font-family:'Geist',Arial,sans-serif}}
main {{max-width:1600px;margin:auto}} header {{font-size:12px;color:{muted};padding:0 40px 16px;letter-spacing:0.08em}}
svg {{width:100%;height:auto;display:block}} svg text {{fill:{ink};font-family:'Geist',Arial,sans-serif;font-size:12px}}
svg .title {{font-family:'Instrument Serif',Georgia,serif;font-size:40px}} svg .subtitle {{font-size:16px;fill:{muted}}}
svg .name {{font-size:16px;font-weight:600}} svg .tag,svg .eyebrow,svg .label {{font-family:'Geist Mono',Consolas,monospace;fill:{muted}}}
svg .tag,svg .eyebrow {{font-size:8px;letter-spacing:0.12em}} svg .label {{font-size:12px}} svg .body {{fill:{muted}}}
footer {{padding:20px 40px 0;font-size:12px;line-height:1.6;color:{muted}}} footer p {{margin:0 0 8px}}
@media print {{body {{padding:0}} footer {{font-size:12px}}}} @media(max-width:800px) {{body {{padding:16px}} .diagram {{overflow:auto}} svg {{min-width:1000px}} header,footer {{padding-left:0;padding-right:0}}}}
</style></head><body><main><header>{name} · MAIN DIAGRAM / REVIEW DRAFT</header><div class="diagram">{svg}</div><footer>
<p>Prometheus scrapes cached collector results every 30 seconds. Grafana evaluates alerts from these measurements. The agent invokes environment-scoped MCP tools; MCP queries named metrics in Prometheus. Collection freshness is reported with the results.</p>
<p>{receipt} Typography: the skill’s Instrument Serif / Geist / Geist Mono; Georgia / Arial / Consolas fallbacks when web fonts are unavailable.</p>
<p>Technology marks: Devicon (MIT), embedded as inline SVG in their original colors. Python marks identify the Python services; AI clients remain provider-neutral.</p>
<p>Browser entry: localhost:3000. The gateway proxies Grafana and checks its session before serving /assistant/ (Streamlit, internal port 8501). The chat calls the internal agent API on port 8000. Grafana embeds the chat in its Ask the fleet dashboard.</p>
<p>Scope: runtime overview. Environment-specific MCP replicas are combined; individual configuration arrows, model-provider calls, CI, SQL provisioning and the .claude toolkit are reserved for detail diagrams. Shared skill settings are unchanged.</p>
</footer></main></body></html>'''
    (ROOT/f'{slug}.html').write_text(html,encoding='utf-8')

build('brand','#f4f5f5','#20262a','#505b61','#303b40','#c4cccf')
build('default','#f5f5f5','#2d3142','#4f5d75','#eb6c36','#f9e9e1')
