"""Skill vocabulary shared by the CV parser and the matching engine.

Each canonical name maps to the spellings that count as the same skill. Bare "C", "R" and
"Go" are left out on purpose: as plain words they match too much. Users add those by hand.
"""

import re

SKILLS: dict[str, list[str]] = {
    # languages
    "Python": ["python"],
    "Java": ["java"],
    "JavaScript": ["javascript", "js"],
    "TypeScript": ["typescript"],
    "C++": ["c++", "cpp"],
    "C#": ["c#", "csharp"],
    "Go": ["golang"],
    "Rust": ["rust"],
    "Kotlin": ["kotlin"],
    "Swift": ["swift"],
    "PHP": ["php"],
    "Ruby": ["ruby"],
    "Dart": ["dart"],
    "Scala": ["scala"],
    "SQL": ["sql"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3"],
    "Bash": ["bash", "shell scripting"],
    "MATLAB": ["matlab"],
    # frontend
    "React": ["react", "reactjs", "react.js"],
    "Next.js": ["next.js", "nextjs"],
    "Angular": ["angular", "angularjs"],
    "Vue.js": ["vue", "vuejs", "vue.js"],
    "Redux": ["redux"],
    "Tailwind CSS": ["tailwind", "tailwindcss", "tailwind css"],
    "Bootstrap": ["bootstrap"],
    "jQuery": ["jquery"],
    "Sass": ["sass", "scss"],
    "Svelte": ["svelte"],
    "Three.js": ["three.js", "threejs"],
    "Framer Motion": ["framer motion"],
    # backend
    "Node.js": ["node.js", "nodejs", "node js", "node"],
    "Express.js": ["express.js", "expressjs", "express js"],
    "Django": ["django"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi"],
    "Spring Boot": ["spring boot", "springboot"],
    ".NET": [".net", "dotnet"],
    "ASP.NET": ["asp.net"],
    "Laravel": ["laravel"],
    "Ruby on Rails": ["ruby on rails", "rails"],
    "NestJS": ["nestjs", "nest.js"],
    "GraphQL": ["graphql"],
    "REST API": ["rest api", "rest apis", "restful api", "restful apis", "restful"],
    "Microservices": ["microservices"],
    "Hibernate": ["hibernate"],
    # databases
    "MySQL": ["mysql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MongoDB": ["mongodb", "mongo db"],
    "SQLite": ["sqlite"],
    "Redis": ["redis"],
    "Oracle Database": ["oracle database", "oracle db"],
    "Firebase": ["firebase"],
    "Supabase": ["supabase"],
    "DynamoDB": ["dynamodb"],
    "Elasticsearch": ["elasticsearch"],
    "Prisma": ["prisma"],
    # cloud / devops
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure"],
    "GCP": ["gcp", "google cloud"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Jenkins": ["jenkins"],
    "Git": ["git"],
    "GitHub": ["github"],
    "GitLab": ["gitlab"],
    "CI/CD": ["ci/cd", "ci cd"],
    "Linux": ["linux"],
    "Terraform": ["terraform"],
    "Ansible": ["ansible"],
    "Nginx": ["nginx"],
    "Vercel": ["vercel"],
    # data / ML
    "Machine Learning": ["machine learning"],
    "Deep Learning": ["deep learning"],
    "NLP": ["nlp", "natural language processing"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "TensorFlow": ["tensorflow"],
    "PyTorch": ["pytorch"],
    "Scikit-learn": ["scikit-learn", "sklearn"],
    "OpenCV": ["opencv"],
    "Spark": ["apache spark", "pyspark", "spark"],
    "Hadoop": ["hadoop"],
    "Power BI": ["power bi", "powerbi"],
    "Tableau": ["tableau"],
    "Excel": ["excel", "ms excel"],
    "Data Analysis": ["data analysis", "data analytics"],
    "Data Structures": ["data structures", "dsa"],
    "Algorithms": ["algorithms"],
    "Generative AI": ["generative ai", "genai", "gen ai"],
    "LLM": ["llm", "llms"],
    "LangChain": ["langchain"],
    # mobile
    "Android": ["android"],
    "iOS": ["ios"],
    "Flutter": ["flutter"],
    "React Native": ["react native"],
    # testing
    "Selenium": ["selenium"],
    "Playwright": ["playwright"],
    "Jest": ["jest"],
    "Cypress": ["cypress"],
    "JUnit": ["junit"],
    "Postman": ["postman"],
    "Manual Testing": ["manual testing"],
    "Automation Testing": ["automation testing", "test automation"],
    "API Testing": ["api testing"],
    # tools / other
    "Figma": ["figma"],
    "Jira": ["jira"],
    "Agile": ["agile"],
    "Scrum": ["scrum"],
    "Photoshop": ["photoshop"],
    "UI/UX": ["ui/ux", "ui ux"],
    "WordPress": ["wordpress"],
    "SEO": ["seo"],
    "Digital Marketing": ["digital marketing"],
    "Tally": ["tally"],
    "AutoCAD": ["autocad"],
    "SAP": ["sap"],
    "Salesforce": ["salesforce"],
}

_ALIAS_TO_CANONICAL = {alias: name for name, aliases in SKILLS.items() for alias in aliases}
_ALIAS_TO_CANONICAL.update({name.lower(): name for name in SKILLS})

# Custom boundaries instead of \b so "c++", "c#" and ".net" work, "java" does not match inside
# "javascript", and "js" does not match inside "node.js".
_PATTERNS = [
    (name, re.compile(rf"(?<![a-z0-9+#.]){re.escape(alias)}(?![a-z0-9+#])", re.IGNORECASE))
    for name, aliases in SKILLS.items()
    for alias in aliases
]


def canonical_skill(name: str) -> str:
    """Map any known spelling to its canonical name; unknown skills pass through trimmed."""
    cleaned = " ".join(name.split())
    return _ALIAS_TO_CANONICAL.get(cleaned.lower(), cleaned)


def find_skills(text: str) -> list[str]:
    """Canonical skills mentioned in free text, in vocabulary order, without duplicates."""
    found: list[str] = []
    for name, pattern in _PATTERNS:
        if name not in found and pattern.search(text):
            found.append(name)
    return found
