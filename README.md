# Escola — Sistema de Gestão Escolar

A Frappe custom app for general school management.

**Language note:** Internal code (app name, module, DocType names, fieldnames, filenames) is in English. All visible UI labels, messages, and section names are in Portuguese (Mozambique/Portugal style).

---

## Requirements

- Frappe v15+
- Python 3.10+

---

## Installation

```bash
# 1. Get the app
bench get-app https://github.com/<your-org>/escola

# 2. Install on your site
bench --site <site-name> install-app escola

# 3. Migrate
bench --site <site-name> migrate
```

After installation, open the **Escola** workspace from the desk.

---

## Phase 1 — Foundation

Phase 1 establishes the core data model and app structure. The following DocTypes are included:

| DocType | UI Label | Purpose |
|---|---|---|
| Academic Year | Ano Lectivo | School academic years |
| School Class | Classe | Grade/class levels |
| Subject | Disciplina | School subjects |
| Teacher | Professor | Teacher profiles |
| Guardian | Encarregado de Educação | Parent/guardian profiles |
| Student | Aluno | Student master records |
| Class Group | Turma | Class groups per academic year |

### Roles created

| Role | Access |
|---|---|
| Diretor Escolar | Full access to all DocTypes |
| Secretaria Escolar | Create/read/write on all core DocTypes |
| Professor | Read-only on core master data |
| Encarregado | No desk access in phase 1 |

---

## Roadmap

**Phase 2 (planned)**
- Class Group student enrollment (child table on Class Group)
- Subject assignment per Class Group or School Class
- Teacher-to-Subject assignment

**Phase 3 (planned)**
- Grade Entry (Pauta de Notas)
- Attendance tracking

**Phase 4 (planned)**
- Reports and print formats
- Annual Assessment workflow
- Student transfer process

---

## License

MIT — see [LICENSE](LICENSE)

## Publisher

EntreTech
