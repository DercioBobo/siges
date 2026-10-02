# SIGES — Sistema Integrado de Gestão Escolar

Plataforma completa de gestão escolar desenvolvida pela **EntreTech**, pensada para a realidade das escolas moçambicanas. Integra a gestão académica, a secretaria e a tesouraria num único sistema, com facturação real (ERPNext) e portais online para encarregados e professores.

---

## 1. Secretaria e Gestão de Alunos

- **Inscrições (Matrículas)**: registo do aluno, do encarregado e da turma num só passo, com verificação de possíveis duplicados.
- **Controlo de documentos**: lista de documentos obrigatórios por aluno (certidão, BI, fotos, etc.) e relatório de documentos pendentes.
- **Renovação de matrícula**: com período de renovação configurável, cobrança automática da taxa e pagamento no acto (POS).
- **Bloqueio automático** de alunos que não renovaram dentro do prazo, e reactivação simples com escolha de turma.
- **Troca de turma**, **transferências** e **desistências**, com histórico completo.
- **Ficha do aluno** com o estado académico e financeiro, a idade actualizada automaticamente e acções rápidas.
- **Encarregados de educação** ligados aos seus educandos.

## 2. Gestão Académica

- **Anos lectivos e trimestres**, com **abertura de novo ano lectivo** assistida e lembretes de fim de ano.
- **Classes e turmas**, com capacidade máxima e nomenclatura automática (ex.: *3ª Classe A-26*).
- **Disciplinas e plano curricular** por turma, com o professor responsável e a carga horária semanal.
- **Professores**, com código automático e as disciplinas que leccionam.
- **Horários**: grelha semanal por turma e turno (Manhã/Tarde), com tempos lectivos configuráveis, salas de aula e cores por disciplina.

## 3. Avaliação e Aproveitamento

- **Lançamento de notas** por turma e disciplina (ACS, ACP e média trimestral), no modelo de avaliação moçambicano.
- **Bloqueio sequencial de trimestres**: não é possível lançar o 2º trimestre sem fechar o 1º.
- **Boletim do aluno**, gerado e actualizado automaticamente, pronto para imprimir.
- **Mapa de aproveitamento** da turma.
- **Avaliação anual** com a nota final, o resultado (Aprovado / Reprovado / Recurso) e o comportamento.
- **Encerramento do ano académico** e **promoção de alunos** para a classe seguinte, com a criação automática das novas turmas.

## 4. Assiduidade e Comportamento

- **Registo de presenças** diário por turma.
- **Pauta de frequência** trimestral com as faltas justificadas e injustificadas.
- **Alerta de alunos em risco** por excesso de faltas.
- **Avaliação do comportamento** por trimestre e por ano.

## 5. Tesouraria e Facturação

- **Facturação automática de propinas**: mensal, trimestral ou anual, conforme a turma.
- **Estruturas de propinas** por classe e **serviços extra** (transporte, cantina, actividades, etc.) com histórico de preços.
- **Multas por atraso** automáticas, com tolerância, percentagem por período e limite máximo configuráveis.
- **Estado financeiro do aluno** actualizado diariamente (Regularizado / Em atraso / Suspenso).
- **Suspensão automática** por falta de pagamento, opcional.
- **Pagamentos adiantados**, com descontos para quem paga vários meses ou o ano inteiro.
- **Desconto para irmãos** (vários alunos do mesmo agregado), configurável.
- **Excepções de pagamento**: prorrogação do prazo para casos específicos.
- **Alunos bolsistas**, isentos de facturação.
- **Central de Pagamentos**: pesquisa rápida de facturas e registo do pagamento em poucos cliques.
- **Monitor de facturas** e **monitor de ciclos de facturação**, com o registo detalhado de cada factura gerada ou ignorada.
- **Pagamento em POS** para inscrições e renovações.
- **IVA** aplicado automaticamente, se a escola o pretender.

## 6. Portais Online

- **Portal do Encarregado**: acesso às notas, ao boletim, às faltas, às facturas e à situação financeira do educando.
- **Portal do Professor**: consulta das turmas e do horário, e lançamento de notas sem entrar no sistema administrativo.

## 7. Relatórios

- Lista da turma
- Resumo de notas e de boletins
- Resumo final da turma e desempenho final por disciplina
- Resumo da avaliação anual e da promoção
- Resumo de presenças
- Resumo de renovações
- Facturação por aluno e lista de facturas
- Resumo dos ciclos de facturação
- Documentos pendentes

Todos os relatórios podem ser filtrados, impressos ou exportados para Excel/PDF.

## 8. Áreas de Trabalho por Perfil

O sistema organiza-se em quatro áreas, cada uma com os atalhos e relatórios relevantes para quem a usa:

| Área | Para quem |
|---|---|
| **Escola** | Direcção: visão geral e configurações |
| **Secretaria** | Matrículas, alunos, turmas, documentos |
| **Professores** | Notas, presenças, horários |
| **Tesouraria** | Facturação, pagamentos, multas |

As permissões são definidas por perfil de utilizador.

## 9. Automatizações Diárias

Todos os dias, sem intervenção manual, o sistema:

- emite as facturas de propinas na data configurada;
- aplica as multas por atraso;
- actualiza o estado financeiro de todos os alunos;
- actualiza os boletins e a idade dos alunos;
- bloqueia os alunos sem renovação dentro do prazo;
- envia lembretes à direcção sobre o fecho e a abertura do ano lectivo.

## 10. Configuração Flexível

Uma única página de **Configurações da Escola** permite adaptar o sistema a cada escola:

- dados da escola, logótipo e director;
- escala de notas, nota mínima de aprovação e limite de faltas;
- taxas de inscrição e de renovação, prazos e dias de emissão das facturas;
- regras de multas, suspensões e descontos;
- activação do portal do encarregado.

---

### Base tecnológica

- Construído sobre **Frappe / ERPNext**, uma plataforma de gestão (ERP) open-source usada em todo o mundo.
- Contabilidade e facturação reais: as facturas, os pagamentos e os clientes ficam integrados na contabilidade.
- Acesso pelo navegador, no computador, tablet ou telemóvel, sem instalação.
- Interface totalmente em **português**.
