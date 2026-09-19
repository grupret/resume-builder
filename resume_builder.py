"""
resume_builder.py — Generic resume tailoring engine.

Works for ANY user whose data is stored in MongoDB.
Pipeline:
  1. Render the Jinja2 template with user data  → base resume text
  2. Call vLLM (gpt-oss-20b) with base + JD     → tailored JSON sections
  3. Build a PDF via ReportLab                   → saved as output/{username}/{job_id}.pdf
"""

import importlib.util
import json
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama

from models import JobDetails, UserResumeCreate

# ── Paths ─────────────────────────────────────────────────────────────────────
SERVICE_DIR  = Path(__file__).parent
RESUMES_DIR  = SERVICE_DIR.parent                      # …/resumes/
TEMPLATE_DIR = SERVICE_DIR / "templates"
OUTPUT_DIR   = RESUMES_DIR / "output"

# ── LLM provider select ────────────────────────────────────────────────────────
LLM_PROVIDER  = os.getenv("LLM_PROVIDER", "vllm").lower()   # "vllm" | "ollama"

# ── vLLM config (from env or defaults matching config.yaml) ───────────────────
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:11434/v1")
VLLM_API_KEY  = os.getenv("VLLM_API_KEY",  "dummy")
VLLM_MODEL    = os.getenv("VLLM_MODEL",    "openai/gpt-oss-20b")
VLLM_TEMP     = float(os.getenv("VLLM_TEMPERATURE", "0.7"))

# ── Ollama config (local system) ───────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL",    "qwen2.5:7b")
OLLAMA_TEMP     = float(os.getenv("OLLAMA_TEMPERATURE", "0.7"))

# ── Jinja2 env ────────────────────────────────────────────────────────────────
_jinja = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), trim_blocks=True, lstrip_blocks=True)

# ── Unicode cleaner ───────────────────────────────────────────────────────────
_CHAR_MAP = str.maketrans({
    "\u25A0": "", "\u25AA": "", "\u25CF": "", "\u25BA": "",
    "\u2192": "->", "\u2013": "-", "\u2014": "-", "\u2011": "-",
    "\u00B7": "", "\u2022": "",
    "\u2018": "'", "\u2019": "'", "\u201C": '"', "\u201D": '"',
    "\u00A0": " ", "\u200B": "",
})

def _clean(text: str) -> str:
    return text.translate(_CHAR_MAP).strip()


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — Render base resume from Jinja2 template
# ══════════════════════════════════════════════════════════════════════════════

def render_base_resume(user: UserResumeCreate) -> str:
    template = _jinja.get_template("resume_base.j2")
    return template.render(user=user)


# ══════════════════════════════════════════════════════════════════════════════
# Step 2 — Generate tailored sections via LLM
# ══════════════════════════════════════════════════════════════════════════════

def build_llm():
    if LLM_PROVIDER == "ollama":
        return ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=OLLAMA_TEMP,
        )

    return ChatOpenAI(
        model=VLLM_MODEL,
        openai_api_key=VLLM_API_KEY,
        openai_api_base=VLLM_BASE_URL,
        temperature=VLLM_TEMP,
        max_tokens=4096,
    )


def generate_tailored_sections(user: UserResumeCreate, job: JobDetails) -> dict:
    """
    Call the LLM to produce tailored resume sections for the given job.

    Returns dict with keys: summary, skills, top_role_bullets, cover_letter_body
    """
    base_resume = render_base_resume(user)

    # Build skill category list from user's data
    skill_labels = ", ".join(s.category for s in user.skills)

    prompt = textwrap.dedent(f"""
        You are an expert resume writer. Tailor the candidate's resume to the job below.

        ## CANDIDATE BASE RESUME
        {base_resume}

        ## TARGET JOB
        Title:    {job.title}
        Company:  {job.company}
        Location: {job.location}
        Seniority: {job.seniority or 'Not specified'}
        Required Skills: {', '.join(job.skills)}

        Job Description:
        {job.description[:5000]}

        ## INSTRUCTIONS
        Produce tailored content for a LEADERSHIP or SENIOR INDIVIDUAL CONTRIBUTOR role.

        Rules:
        1. SUMMARY (2-3 sentences): Mirror the JD language. Lead with seniority and domain.
           No filler phrases. Do NOT mention specific tool names or frameworks.

        2. SKILLS (list of [label, value] pairs): Use ONLY these category names: {skill_labels}.
           Reorder to put the most JD-relevant skills first.
           Write abstract capability phrases, NEVER specific tool names.

        3. TOP_ROLE_BULLETS (6-7 strings for the most recent role):
           Rewrite bullets to match this JD. Outcomes and leadership focus.
           NEVER name specific clients. NEVER include customer growth counts.
           Use abstract scale: "enterprise-grade workloads", "multi-tenant platform", etc.
           Past tense. One complete sentence per bullet. No repeated opening verbs.

        4. COVER_LETTER_BODY (~180 words, 3 paragraphs): Professional tone.
           Same no-client-name and no-count rules apply.

        FORMATTING (critical):
        
        - Strictly Follow proper camel casing on for all Skills in bullets under TECHNICAL SKILLS.
        - Plain ASCII only. No Unicode symbols (no ■ ▪ ● — etc.).
        - No bullet prefix characters in the JSON strings.
        - Plain hyphens (-) for dashes.
        - Fix all spelling and grammar before output.\

        Return ONLY valid JSON:
        {{
          "summary": "<string>",
          "skills": [["<label>", "<value>"], ...],
          "top_role_bullets": ["<bullet>", ...],
          "cover_letter_body": "<string>"
        }}
    """).strip()

    llm      = build_llm()
    response = llm.invoke([HumanMessage(content=prompt)])
    content  = response.content

    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError(f"LLM did not return valid JSON. Raw output:\n{content[:500]}")

    parsed = json.loads(match.group())

    # Clean all text fields
    parsed["summary"] = _clean(parsed.get("summary", ""))
    parsed["skills"]  = [
        [_clean(label), _clean(val)]
        for label, val in parsed.get("skills", [])
    ]
    parsed["top_role_bullets"] = [
        _clean(b) for b in parsed.get("top_role_bullets", [])
    ]
    parsed["cover_letter_body"] = _clean(parsed.get("cover_letter_body", ""))

    return parsed


# ══════════════════════════════════════════════════════════════════════════════
# Step 3 — Build PDF
# ══════════════════════════════════════════════════════════════════════════════

def _load_resume_module():
    """Import resume.py from the parent directory via importlib."""
    resume_path = RESUMES_DIR / "resume.py"
    spec = importlib.util.spec_from_file_location("resume", str(resume_path))
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_pdf(
    user: UserResumeCreate,
    sections: dict,
    job: JobDetails,
    output_path: str,
) -> str:
    """
    Build a tailored PDF from user data + LLM-generated sections.
    Uses resume.py's build_customized_pdf() and ReportLab styles.
    Returns the output_path on success.
    """
    resume_mod = _load_resume_module()

    # Map user skills to (label, value) tuples as resume.py expects
    skill_tuples = (
        [tuple(pair) for pair in sections["skills"]]
        if sections.get("skills")
        else [(s.category, s.values) for s in user.skills]
    )

    # Rebuild the top role's bullets with tailored content
    experience = [
        {
            "role":    exp.role,
            "company": exp.company,
            "dates":   exp.dates,
            "bullets": (
                sections["top_role_bullets"]
                if i == 0 and sections.get("top_role_bullets")
                else exp.bullets
            ),
        }
        for i, exp in enumerate(user.experience)
    ]

    # Build contact HTML string
    contact_parts = [f"<a href='mailto:{user.email}' color='#1A3A5C'>{user.email}</a>"]
    if user.phone:
        contact_parts.append(f"<a href='tel:{user.phone}' color='#1A3A5C'>{user.phone}</a>")
    if user.linkedin_url:
        display = user.linkedin_url.replace("https://", "").replace("http://", "")
        contact_parts.append(f"<a href='{user.linkedin_url}' color='#1A3A5C'>{display}</a>")
    if user.github_url:
        display = user.github_url.replace("https://", "").replace("http://", "")
        contact_parts.append(f"<a href='{user.github_url}' color='#1A3A5C'>{display}</a>")

    data = {
        "name":       user.name,
        "contact":    "  ·  ".join(contact_parts),
        "summary":    sections.get("summary") or user.summary,
        "skills":     skill_tuples,
        "experience": experience,
        "certs":      user.certifications,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    resume_mod.build_customized_pdf(data, output_path)
    return output_path


# ══════════════════════════════════════════════════════════════════════════════
# Full pipeline
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline(
    user: UserResumeCreate,
    job: JobDetails,
    output_override: Optional[str] = None,
) -> dict:
    """
    Full tailoring pipeline: generate sections → build PDF → save cover letter.

    Returns:
        {
          "pdf_path":          str,
          "cover_letter_path": str | None,
          "sections":          dict   (summary, skills, bullets)
        }
    """
    sections = generate_tailored_sections(user, job)

    slug       = f"{job.company}_{job.title}_{job.job_id}".replace(" ", "_").replace("/", "-")[:80]
    out_dir    = OUTPUT_DIR / user.username
    pdf_path   = output_override or str(out_dir / f"{job.job_id}.pdf")
    cl_path    = str(out_dir / f"{job.job_id}_cover_letter.txt")

    build_pdf(user, sections, job, pdf_path)

    cover_letter_path = None
    if sections.get("cover_letter_body"):
        Path(cl_path).parent.mkdir(parents=True, exist_ok=True)
        Path(cl_path).write_text(
            f"Cover Letter — {job.title} @ {job.company}\n"
            f"{'=' * 60}\n\n"
            + sections["cover_letter_body"]
        )
        cover_letter_path = cl_path

    return {
        "pdf_path":          pdf_path,
        "cover_letter_path": cover_letter_path,
        "sections":          sections,
    }


# ══════════════════════════════════════════════════════════════════════════════
# LinkedIn job fetcher (reused from linkedin_agent)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_job_from_linkedin(job_id: str, username: str, password: str,
                             li_at: str = "", jsessionid: str = "") -> JobDetails:
    """Authenticate to LinkedIn and return a JobDetails object."""
    from linkedin_api import Linkedin

    if li_at and jsessionid:
        client = Linkedin("", "", cookies={"li_at": li_at, "JSESSIONID": jsessionid})
    else:
        client = Linkedin(username, password)

    raw = client.get_job(job_id)

    desc_raw = raw.get("description", {}).get("text", "")
    desc     = "\n".join(line for line in desc_raw.splitlines() if line.strip())

    company = (
        raw.get("companyDetails", {})
        .get("com.linkedin.voyager.deco.jobs.web.shared.WebCompactJobPostingCompany", {})
        .get("companyResolutionResult", {})
        .get("name", "")
    )

    return JobDetails(
        job_id      = job_id,
        title       = raw.get("title", ""),
        company     = company,
        location    = raw.get("formattedLocation", ""),
        seniority   = raw.get("expLevel", ""),
        employment  = raw.get("employmentStatus", ""),
        apply_url   = f"https://www.linkedin.com/jobs/view/{job_id}/",
        easy_apply  = bool(
            raw.get("applyMethod", {}).get(
                "com.linkedin.voyager.jobs.ComplexOnsiteApply"
            )
        ),
        description = desc[:8000],
        skills      = [s.get("name", "") for s in raw.get("skills", [])],
    )
