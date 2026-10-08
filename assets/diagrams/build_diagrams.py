"""
Generates one draw.io architecture diagram per workshop module (house style:
aws4 resourceIcon 78x78 with white stroke, solid groups, black orthogonal
arrows, red annotations) and exports PNGs (DPI-400, border 15).

Usage:
    python assets/diagrams/build_diagrams.py            # .drawio + final PNGs
    python assets/diagrams/build_diagrams.py --preview  # fast cropped previews
"""

import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PORTAL_DIR = ROOT / "frontend" / "public" / "diagrams"
DRAWIO = "/Applications/draw.io.app/Contents/MacOS/draw.io"

POINTS = "points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];"
COLORS = {"net": "#8C4FFF", "compute": "#ED7100", "api": "#E7157B", "storage": "#7AA116", "ai": "#01A88D", "sec": "#DD344C", "mgmt": "#E7157B"}
GROUPS = {
    "aws": ("#ffe6cc", "#d79b00", 3),
    "green": ("#d5e8d4", "#82b366", 6),
    "purple": ("#e1d5e7", "#9673a6", 6),
    "blue": ("#dae8fc", "#6c8ebf", 6),
    "red": ("#f8cecc", "#b85450", 6),
}
TEXT = "text;html=1;align=center;verticalAlign=middle;resizable=0;points=[];autosize=1;strokeColor=none;fillColor=none;"


class Diagram:
    def __init__(self, name: str, title: str, width: int = 1200, height: int = 560):
        self.name, self.title, self.width, self.height = name, title, width, height
        self.cells: list[str] = []
        self.n = 0

    def _id(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}{self.n}"

    def _vertex(self, cid, style, x, y, w, h, value=""):
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(value, {chr(34): "&quot;"})}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
        )
        return cid

    def group(self, kind, x, y, w, h, title=""):
        fill, stroke, arc = GROUPS[kind]
        gid = self._vertex(self._id("g"), f"rounded=1;whiteSpace=wrap;html=1;arcSize={arc};fillColor={fill};strokeColor={stroke};", x, y, w, h)
        if title:
            self._vertex(self._id("gt"), TEXT + "fontSize=14;fontStyle=1;align=left;", x + 12, y + 4, max(120, len(title) * 8), 26, title)
        return gid

    def icon(self, x, y, res, color, label, size=78):
        style = (
            f"sketch=0;{POINTS}outlineConnect=0;fontColor=#232F3E;fillColor={COLORS[color]};strokeColor=#ffffff;dashed=0;"
            f"verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;"
            f"shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.{res};"
        )
        cid = self._vertex(self._id("i"), style, x, y, size, size)
        lines = label.count("\n") + 1
        self._vertex(self._id("l"), TEXT + "fontSize=12;", x + size / 2 - 75, y + size + 2, 150, 18 * lines, label.replace("\n", "<br>"))
        return cid

    def actor(self, x, y, label="Participante"):
        cid = self._vertex(self._id("a"), "shape=actor;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;", x, y, 40, 60)
        self._vertex(self._id("l"), TEXT + "fontSize=12;", x - 30, y + 62, 100, 20, label)
        return cid

    def note(self, x, y, text, color="#FF0000", size=12, bold=True):
        style = TEXT + f"fontColor={color};fontSize={size};" + ("fontStyle=1;" if bold else "")
        lines = text.count("\n") + 1
        return self._vertex(self._id("n"), style, x, y, max(60, max(len(t) for t in text.split("\n")) * 7), 18 * lines, text.replace("\n", "<br>"))

    def edge(self, src, dst, exit=(1, 0.5), entry=(0, 0.5), points=(), dashed=False):
        style = (
            "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"
            f"exitX={exit[0]};exitY={exit[1]};exitDx=0;exitDy=0;entryX={entry[0]};entryY={entry[1]};entryDx=0;entryDy=0;"
            + ("dashed=1;" if dashed else "")
        )
        pts = "".join(f'<mxPoint x="{px}" y="{py}"/>' for px, py in points)
        geometry = f'<mxGeometry relative="1" as="geometry"><Array as="points">{pts}</Array></mxGeometry>' if pts else '<mxGeometry relative="1" as="geometry"/>'
        self.cells.append(f'<mxCell id="{self._id("e")}" style="{style}" edge="1" parent="1" source="{src}" target="{dst}">{geometry}</mxCell>')

    def save(self) -> Path:
        title = self._vertex("title", TEXT + "fontSize=18;fontStyle=1;fontColor=#232F3E;align=left;", 20, 8, self.width - 40, 30, self.title)
        _ = title
        body = "".join(self.cells[-1:] + self.cells[:-1])  # title first
        xml = (
            f'<mxfile host="build_diagrams.py"><diagram name="{self.name}" id="{self.name}">'
            f'<mxGraphModel dx="1400" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
            f'pageWidth="{self.width}" pageHeight="{self.height}" math="0" shadow="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
            f"{body}</root></mxGraphModel></diagram></mxfile>"
        )
        path = HERE / f"{self.name}.drawio"
        path.write_text(xml, encoding="utf-8")
        return path


# ------------------------------------------------------------------ diagrams
def m00():
    d = Diagram("00-setup", "Módulo 00 · Preparar el entorno (infraestructura base con AWS CDK)", 1200, 560)
    d.group("aws", 290, 50, 890, 480, "AWS Cloud · us-east-1")
    d.group("purple", 320, 90, 170, 420, "Validación")
    found = d.group("green", 540, 90, 610, 420, "Stack foundation (CDK)")
    user = d.actor(30, 255)
    ide = d.icon(140, 245, "sagemaker", "ai", "IDE\nVS Code / SageMaker")
    sts = d.icon(366, 130, "identity_and_access_management", "sec", "AWS STS\n(identidad)")
    br = d.icon(366, 260, "bedrock", "ai", "Amazon Bedrock\n6 modelos")
    cfn = d.icon(366, 390, "cloudformation", "mgmt", "CloudFormation\noutputs")
    d.icon(580, 140, "s3", "storage", "S3 docs\n(Knowledge Base)")
    d.icon(580, 330, "s3", "storage", "S3 artifacts\n(agent zips)")
    apigw = d.icon(780, 140, "api_gateway", "api", "API Gateway\n(AWS_IAM)")
    lam = d.icon(980, 140, "lambda", "compute", "Lambda\nAPI bancaria")
    d.icon(780, 330, "identity_and_access_management", "sec", "Roles IAM\nKB · GW · Harness · Runtime")
    d.icon(980, 330, "cloudfront", "net", "CloudFront + S3\n(portal OAC)")
    d.edge(user, ide)
    d.edge(ide, sts, exit=(1, 0.2), entry=(0, 0.5), points=[(260, 261), (260, 169)])
    d.edge(ide, br, exit=(1, 0.5), entry=(0, 0.5), points=[(260, 284), (260, 299)])
    d.edge(ide, cfn, exit=(1, 0.8), entry=(0, 0.5), points=[(260, 307), (260, 429)])
    d.edge(cfn, found, exit=(1, 0.5), entry=(0, 0.825))
    d.edge(apigw, lam)
    d.note(120, 205, "boto3 + credenciales")
    d.note(700, 470, "cdk deploy (facilitador)")
    return d


def m01():
    d = Diagram("01-bedrock-llms", "Módulo 01 · Amazon Bedrock: input / output de un LLM (Converse API)", 1150, 440)
    d.group("aws", 290, 50, 840, 360, "AWS Cloud · us-east-1")
    d.group("purple", 590, 90, 260, 290, "Foundation Model")
    user = d.actor(30, 175)
    ide = d.icon(140, 165, "sagemaker", "ai", "IDE\nnotebook 01")
    conv = d.icon(380, 165, "bedrock", "ai", "Bedrock Runtime\nConverse / ConverseStream")
    llm = d.icon(680, 165, "bedrock", "ai", "Claude Haiku\n(FAST_MODEL_ID)")
    cw = d.icon(960, 165, "cloudwatch_2", "api", "CloudWatch\nmétricas de invocación")
    d.edge(user, ide)
    d.edge(ide, conv, exit=(1, 0.3), entry=(0, 0.3))
    d.edge(conv, ide, exit=(0, 0.7), entry=(1, 0.7))
    d.edge(conv, llm)
    d.edge(llm, cw)
    d.note(222, 125, "system + messages[]\nmaxTokens")
    d.note(160, 300, "output · usage · metrics · stopReason")
    d.note(865, 145, "tokens / latencia")
    d.note(625, 300, "stateless: reenvía el historial", "#232F3E", 11, False)
    return d


def m02():
    d = Diagram("02-model-battle", "Módulo 02 · Batalla de cerebros: OpenAI vs Claude en Amazon Bedrock", 1250, 560)
    d.group("aws", 290, 50, 940, 480, "AWS Cloud · us-east-1")
    oa = d.group("blue", 560, 85, 420, 190, "OpenAI en Bedrock")
    cl = d.group("purple", 560, 310, 420, 190, "Anthropic en Bedrock")
    user = d.actor(30, 265)
    ide = d.icon(140, 255, "sagemaker", "ai", "IDE\nnotebook 02")
    conv = d.icon(360, 255, "bedrock", "ai", "Converse API\n(misma interfaz)")
    for i, label in enumerate(["GPT-5.6 Luna", "GPT-5.6 Terra", "GPT-5.6 Sol"]):
        d.icon(600 + i * 130, 130, "bedrock", "ai", label)
    for i, label in enumerate(["Claude Haiku\n(FAST_MODEL_ID)", "Claude Sonnet\n(DEFAULT_MODEL_ID)", "Claude Opus\n(TOP_MODEL_ID)"]):
        d.icon(600 + i * 130, 355, "bedrock", "ai", label)
    judge = d.icon(1090, 255, "bedrock", "ai", "Juez Claude Opus\nLLM-as-a-Judge")
    d.edge(user, ide)
    d.edge(ide, conv)
    d.edge(conv, oa, exit=(1, 0.25), entry=(0, 0.5), points=[(500, 274), (500, 180)])
    d.edge(conv, cl, exit=(1, 0.75), entry=(0, 0.5), points=[(500, 313), (500, 405)])
    d.edge(oa, judge, exit=(1, 0.5), entry=(0, 0.25), points=[(1040, 180), (1040, 274)])
    d.edge(cl, judge, exit=(1, 0.5), entry=(0, 0.75), points=[(1040, 405), (1040, 313)])
    d.note(340, 380, "6 llamadas en paralelo")
    d.note(1060, 225, "score 0-10")
    d.note(1010, 470, "calidad vs latencia vs tokens", "#232F3E", 11, False)
    return d


def m03():
    d = Diagram("03-guardrails", "Módulo 03 · Amazon Bedrock Guardrails (tier STANDARD, multilenguaje)", 1250, 560)
    d.group("aws", 290, 50, 940, 480, "AWS Cloud · us-east-1")
    d.group("red", 320, 90, 200, 420, "Guardrail · INPUT")
    d.group("purple", 570, 90, 230, 420, "Modelos")
    d.group("red", 850, 90, 200, 420, "Guardrail · OUTPUT")
    user = d.actor(30, 175)
    ide = d.icon(140, 165, "sagemaker", "ai", "IDE\nnotebook 03")
    gin = d.icon(381, 165, "waf", "sec", "Prompt attack · Topics\nWords · PII")
    llm = d.icon(646, 165, "bedrock", "ai", "Claude Haiku\nConverse + guardrailConfig")
    gout = d.icon(911, 165, "waf", "sec", "PII ANONYMIZE\nWord filters")
    apply_ = d.icon(381, 375, "waf", "sec", "ApplyGuardrail API\n(sin modelo)")
    oai = d.icon(646, 375, "bedrock", "ai", "GPT-5.6 Luna\n(otro proveedor)")
    cw = d.icon(1110, 165, "cloudwatch_2", "api", "Trazas /\nassessments")
    d.edge(user, ide)
    d.edge(ide, gin)
    d.edge(gin, llm)
    d.edge(llm, gout)
    d.edge(gout, cw)
    d.edge(ide, apply_, exit=(1, 0.8), entry=(0, 0.5), points=[(270, 227), (270, 414)])
    d.edge(apply_, oai)
    d.note(530, 140, "✅ pasa")
    d.note(340, 300, "❌ bloquea → mensaje seguro", size=11)
    d.note(808, 140, "🎭 {EMAIL} {PHONE}")
    d.note(530, 350, "agnóstico al modelo")
    return d


def m04():
    d = Diagram("04-rag", "Módulo 04 · RAG con Amazon Bedrock Managed Knowledge Base", 1250, 600)
    d.group("aws", 290, 50, 940, 520, "AWS Cloud · us-east-1")
    d.group("blue", 320, 90, 880, 200, "2. Consulta")
    d.group("green", 320, 330, 880, 210, "1. Ingesta (CDK sube los docs a S3)")
    user = d.actor(30, 165)
    ide = d.icon(140, 155, "sagemaker", "ai", "IDE\nnotebook 04")
    ret = d.icon(400, 155, "bedrock", "ai", "Retrieve /\nAgenticRetrieveStream")
    llm = d.icon(820, 155, "bedrock", "ai", "Generación\ncon citas")
    kb = d.icon(400, 400, "bedrock", "ai", "Managed Knowledge Base\nhíbrida + rerank")
    ing = d.icon(640, 400, "bedrock", "ai", "Ingestion job\nparsing · chunks · embeddings")
    s3 = d.icon(880, 400, "s3", "storage", "S3 docs\n6 FAQs ficticias")
    role = d.icon(1090, 400, "identity_and_access_management", "sec", "Rol KB\n(S3 read)")
    d.edge(user, ide)
    d.edge(ide, ret)
    d.edge(ret, llm)
    d.edge(ret, kb, exit=(0, 0.8), entry=(0, 0.5), points=[(305, 217), (305, 439)])
    d.edge(s3, ing, exit=(0, 0.5), entry=(1, 0.5))
    d.edge(ing, kb, exit=(0, 0.5), entry=(1, 0.5))
    d.edge(role, s3, exit=(0, 0.5), entry=(1, 0.5), dashed=True)
    d.note(560, 170, "top-k chunks")
    d.note(312, 300, "RAG")
    d.note(780, 375, "sync")
    return d


def m05():
    d = Diagram("05-harness", "Módulo 05 · AgentCore Harness: el agente gestionado (solo configuración)", 1250, 600)
    d.group("aws", 290, 50, 940, 520, "AWS Cloud · us-east-1")
    d.group("purple", 320, 90, 470, 450, "AgentCore Harness (microVM por sesión)")
    d.group("green", 840, 90, 360, 450, "Modelos (override por invocación)")
    user = d.actor(30, 265)
    ide = d.icon(140, 255, "sagemaker", "ai", "IDE · InvokeHarness\nsessionId + actorId")
    h = d.icon(370, 255, "bedrock", "ai", "Harness\nciclo gestionado (Strands)")
    ci = d.icon(620, 130, "bedrock", "ai", "Code Interpreter\n(Python sandbox)")
    mem = d.icon(620, 400, "bedrock", "ai", "Managed Memory\nSTM + LTM por actorId")
    son = d.icon(880, 150, "bedrock", "ai", "Claude Sonnet\n(default)")
    d.icon(1080, 150, "bedrock", "ai", "Claude Haiku\n(override)")
    gpt = d.icon(880, 390, "bedrock", "ai", "GPT-5.6 Sol\n(sesión nueva)")
    d.icon(1080, 390, "cloudwatch_2", "api", "Observabilidad\nCloudWatch")
    d.edge(user, ide)
    d.edge(ide, h)
    d.edge(h, ci, exit=(1, 0.15), entry=(0, 0.5), points=[(540, 267), (540, 169)])
    d.edge(h, mem, exit=(1, 0.85), entry=(0, 0.5), points=[(540, 321), (540, 439)])
    d.edge(h, son, exit=(1, 0.4), entry=(0, 0.5), points=[(815, 286), (815, 189)])
    d.edge(h, gpt, exit=(1, 0.6), entry=(0, 0.5), points=[(828, 302), (828, 429)])
    d.note(548, 215, "tools")
    d.note(978, 180, "mismo contexto")
    d.note(660, 268, "modelo")
    return d


def m06():
    d = Diagram("06-gateway-websearch", "Módulo 06 · AgentCore Gateway (MCP) + Web Search", 1250, 560)
    d.group("aws", 290, 50, 940, 480, "AWS Cloud · us-east-1")
    d.group("purple", 320, 150, 200, 375, "Agente")
    d.group("blue", 570, 150, 400, 375, "AgentCore Gateway")
    user = d.actor(30, 255)
    ide = d.icon(140, 245, "sagemaker", "ai", "IDE\nnotebook 06")
    h = d.icon(381, 245, "bedrock", "ai", "Harness\n(módulo 05)")
    gw = d.icon(640, 245, "bedrock", "ai", "Gateway MCP\nAWS_IAM · SEMANTIC")
    ws = d.icon(850, 245, "bedrock", "ai", "Target: Web Search\n(connector gestionado)")
    role = d.icon(640, 400, "identity_and_access_management", "sec", "Rol Gateway\nInvokeWebSearch")
    web = d.icon(1090, 245, "cloudfront", "net", "Índice web\n(dentro de AWS)")
    d.edge(user, ide)
    d.edge(ide, h)
    d.edge(h, gw)
    d.edge(gw, ws)
    d.edge(ws, web)
    d.edge(ide, gw, exit=(0.5, 0), entry=(0.5, 0), points=[(179, 120), (679, 120)])
    d.edge(gw, role, exit=(0, 0.8), entry=(0, 0.5), dashed=True, points=[(610, 307), (610, 439)])
    d.note(330, 96, "MCP tools/list + tools/call (SigV4) 'a mano'")
    d.note(530, 225, "MCP")
    d.note(975, 225, "web search")
    return d


def m07():
    d = Diagram("07-runtime-strands", "Módulo 07 · Strands Agents en AgentCore Runtime (direct code deploy)", 1250, 600)
    d.group("aws", 290, 50, 940, 520, "AWS Cloud · us-east-1")
    d.group("purple", 560, 90, 370, 450, "AgentCore Runtime")
    user = d.actor(30, 165)
    ide = d.icon(140, 155, "sagemaker", "ai", "IDE\nagent_v07.py (Strands)")
    role = d.icon(370, 290, "identity_and_access_management", "sec", "Rol Runtime\n(least privilege)")
    s3 = d.icon(370, 420, "s3", "storage", "S3 artifacts\nzip ARM64 (~49 MB)")
    rt = d.icon(670, 155, "bedrock", "ai", "Runtime HTTP\n/invocations · /ping")
    tools = d.icon(800, 420, "lambda", "compute", "@tool locales\ncuota · tasa mensual")
    llm = d.icon(1040, 155, "bedrock", "ai", "Claude Sonnet\n(Bedrock)")
    d.icon(1040, 420, "cloudwatch_2", "api", "GenAI Observability\n(OpenTelemetry)")
    d.edge(user, ide)
    d.edge(ide, rt)
    d.edge(ide, s3, exit=(1, 0.8), entry=(0, 0.5), points=[(280, 217), (280, 459)])
    d.edge(s3, rt, exit=(1, 0.5), entry=(0, 0.95), points=[(620, 459), (620, 229)])
    d.edge(role, rt, exit=(1, 0.5), entry=(0, 0.8), dashed=True, points=[(600, 329), (600, 217)])
    d.edge(rt, tools, exit=(1, 0.75), entry=(0.5, 0), points=[(839, 213)])
    d.edge(rt, llm)
    d.note(400, 170, "InvokeAgentRuntime (SigV4)")
    d.note(300, 545, "1. pip --platform aarch64 → zip → S3")
    d.note(470, 470, "2. codeConfiguration")
    d.note(1010, 545, "trazas · spans · tokens", "#232F3E", 11, False)
    return d


def m08():
    d = Diagram("08-runtime-gateway-api", "Módulo 08 · Runtime + Gateway + API backend (API Gateway + Lambda)", 1350, 560)
    d.group("aws", 290, 50, 1040, 480, "AWS Cloud · us-east-1")
    d.group("purple", 320, 90, 190, 420, "AgentCore Runtime")
    d.group("blue", 560, 90, 370, 420, "AgentCore Gateway")
    d.group("green", 980, 230, 330, 280, "Backend privado (CDK)")
    user = d.actor(30, 275)
    ide = d.icon(140, 265, "sagemaker", "ai", "IDE\nnotebook 08")
    rt = d.icon(376, 265, "bedrock", "ai", "Agente v08\nStrands + MCPClient")
    gw = d.icon(620, 265, "bedrock", "ai", "Gateway MCP\n(SigV4)")
    t_api = d.icon(810, 265, "api_gateway", "api", "Target banking-api\ntoolOverrides")
    t_ws = d.icon(810, 120, "bedrock", "ai", "Target web-search")
    apigw = d.icon(1020, 265, "api_gateway", "api", "API Gateway REST\nAWS_IAM")
    lam = d.icon(1200, 265, "lambda", "compute", "Lambda\nAPI bancaria ficticia")
    role = d.icon(620, 392, "identity_and_access_management", "sec", "Rol Gateway\nexecute-api:Invoke")
    d.edge(user, ide)
    d.edge(ide, rt)
    d.edge(rt, gw)
    d.edge(gw, t_api)
    d.edge(gw, t_ws, exit=(0.5, 0), entry=(0, 0.5), points=[(659, 159)])
    d.edge(t_api, apigw)
    d.edge(apigw, lam)
    d.edge(gw, role, exit=(0, 0.8), entry=(0, 0.5), dashed=True, points=[(590, 327), (590, 431)])
    d.note(520, 245, "MCP")
    d.note(930, 245, "SigV4")
    d.note(1000, 390, "sin firma → HTTP 403", "#232F3E", 11, False)
    return d


def m09():
    d = Diagram("09-final-agent", "Módulo 09 · Agente final: Runtime + Gateway + RAG + Guardrails", 1400, 640)
    d.group("aws", 290, 50, 1090, 560, "AWS Cloud · us-east-1")
    d.group("purple", 320, 90, 360, 490, "AgentCore Runtime · agente v09")
    d.group("blue", 730, 90, 200, 490, "AgentCore Gateway")
    d.group("green", 980, 90, 370, 490, "Herramientas")
    user = d.actor(30, 285)
    ide = d.icon(140, 275, "sagemaker", "ai", "Cliente / IDE\nInvokeAgentRuntime")
    rt = d.icon(370, 275, "bedrock", "ai", "Strands Agent\n(Runtime)")
    gr = d.icon(550, 130, "waf", "sec", "ApplyGuardrail\nINPUT + OUTPUT")
    llm = d.icon(550, 430, "bedrock", "ai", "Claude Sonnet\n(DEFAULT_MODEL_ID)")
    gw = d.icon(791, 275, "bedrock", "ai", "Gateway MCP\n3 targets")
    ws = d.icon(1020, 130, "bedrock", "ai", "Web Search")
    api = d.icon(1020, 275, "api_gateway", "api", "API bancaria\nAPI Gateway")
    kb = d.icon(1020, 430, "bedrock", "ai", "Managed KB\n(Retrieve)")
    s3 = d.icon(1220, 430, "s3", "storage", "S3 docs")
    lam = d.icon(1220, 275, "lambda", "compute", "Lambda")
    d.edge(user, ide)
    d.edge(ide, rt)
    d.edge(rt, gr, exit=(0.5, 0), entry=(0, 0.5), points=[(409, 169)])
    d.edge(rt, llm, exit=(0, 0.8), entry=(0, 0.5), points=[(345, 337), (345, 469)])
    d.edge(rt, gw)
    d.edge(gw, ws, exit=(1, 0.2), entry=(0, 0.5), points=[(960, 291), (960, 169)])
    d.edge(gw, api)
    d.edge(gw, kb, exit=(1, 0.8), entry=(0, 0.5), points=[(960, 337), (960, 469)])
    d.edge(api, lam)
    d.edge(kb, s3)
    d.note(425, 258, "🛡️ antes y después")
    d.note(690, 255, "MCP")
    d.note(905, 140, "web")
    d.note(905, 500, "RAG")
    d.note(1130, 255, "SigV4")
    return d


BUILDERS = [m00, m01, m02, m03, m04, m05, m06, m07, m08, m09]


def render(path: Path, preview: bool) -> Path:
    out = HERE / ("_preview" if preview else "png") / f"{path.stem}.png"
    out.parent.mkdir(exist_ok=True)
    args = [DRAWIO, "-x", "-f", "png", "-o", str(out), str(path)]
    args[4:4] = ["-s", "2", "--crop"] if preview else ["-s", "4.17", "-b", "15"]
    subprocess.run(args, check=True, capture_output=True)
    return out


if __name__ == "__main__":
    preview = "--preview" in sys.argv
    PORTAL_DIR.mkdir(parents=True, exist_ok=True)
    for build in BUILDERS:
        drawio = build().save()
        png = render(drawio, preview)
        if not preview:
            shutil.copy(png, PORTAL_DIR / png.name)
        print(f"✅ {drawio.name} -> {png.relative_to(ROOT)}")
