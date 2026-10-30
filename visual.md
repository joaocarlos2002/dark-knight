# QA Workbench --- Especificação visual da TUI

**Documento:** `docs/design/tui-screen-spec.md`\
**Objetivo:** orientar o Codex na implementação visual das telas do QA
Workbench usando Textual.\
**Interface:** TUI pura, navegável por teclado.\
**Referência:** wireframes conceituais em caracteres; não representam
dimensões fixas nem implementação final.

------------------------------------------------------------------------

# 1. Direção visual

O QA Workbench deve ter uma interface terminal-first, técnica e
discreta, inspirada em ferramentas de desenvolvimento como OpenCode. A
interface deve priorizar densidade de informação, legibilidade,
hierarquia visual e navegação rápida.

Princípios: - Layout consistente entre módulos. - Sidebar persistente. -
Área central dedicada à tarefa atual. - Painel contextual opcional. -
Barra inferior com estado do projeto e atalhos. - Cores usadas para
comunicar estado, não como decoração. - Todos os estados devem ser
compreensíveis também sem cor. - Layout adaptável a terminais menores. -
Evitar excesso de bordas, caixas e elementos visuais simultâneos.

# 2. Recomendação de cores

## 2.1 Tema principal: Dark

Usar tema escuro como padrão. Os valores abaixo são referências
hexadecimais; adaptar para a paleta suportada pelo terminal e pelo
Textual.

  ------------------------------------------------------------------------
  Função           Cor                       Hex sugerido Uso
  ---------------- ---------------- --------------------- ----------------
  Fundo principal  Quase preto                  `#101216` Fundo da
                                                          aplicação

  Fundo secundário Grafite                      `#171B22` Sidebar e
                                                          painéis

  Fundo elevado    Cinza escuro                 `#202631` Modais, seleção
                                                          e áreas
                                                          destacadas

  Borda discreta   Cinza azulado                `#303846` Separadores e
                                                          contornos

  Texto principal  Branco suave                 `#E6EAF0` Conteúdo
                                                          principal

  Texto secundário Cinza                        `#A0A9B8` Metadados e
                                                          descrições

  Texto            Cinza escuro                 `#687386` Ações
  desabilitado                                            indisponíveis

  Accent / seleção Azul                         `#6EA8FE` Foco, seleção e
                                                          links internos

  Informação       Ciano                        `#56B6C2` Eventos
                                                          informativos

  Sucesso          Verde                        `#69C58B` Passed, Success,
                                                          conectado

  Atenção          Âmbar                        `#E5B567` Pending,
                                                          Warning,
                                                          aprovação
                                                          necessária

  Falha            Vermelho                     `#E06C75` Failed, erro e
                                                          bloqueio crítico

  IA               Roxo                         `#B69AE8` Agente,
                                                          sugestões e
                                                          operações de IA
  ------------------------------------------------------------------------

## 2.2 Semântica de status

  Estado                        Cor                                      Texto/símbolo
  ----------------------------- ---------------------------------------- -------------------------
  Passed / Success              Verde                                    `✓ PASSED`
  Failed / Error                Vermelho                                 `✗ FAILED`
  Running                       Azul ou ciano                            `● RUNNING`
  Pending / Awaiting approval   Âmbar                                    `◷ PENDING`
  Blocked                       Âmbar ou vermelho, conforme severidade   `⊘ BLOCKED`
  Inconclusive                  Cinza ou âmbar                           `? INCONCLUSIVE`
  Cancelled                     Cinza                                    `■ CANCELLED`
  Skipped                       Cinza                                    `– SKIPPED`
  AI activity                   Roxo                                     `✦ AI`
  Selected/focused              Azul                                     `>` ou destaque de foco

Não usar vermelho para todo estado negativo: `Blocked`, `Inconclusive` e
`Cancelled` não são equivalentes a `Failed`.

## 2.3 Regras de aplicação

- Azul deve indicar foco, seleção ou navegação ativa.
- Verde deve ser reservado a resultados positivos.
- Vermelho deve indicar falha real ou erro que exige atenção.
- Âmbar deve indicar atenção, pendência ou aprovação.
- Roxo deve identificar recursos de IA, sem sugerir que uma recomendação
  da IA é um resultado confirmado.
- Texto secundário não pode ter contraste baixo a ponto de prejudicar a
  leitura.
- Não depender apenas da cor: sempre exibir o nome do estado e, quando
  útil, um símbolo.
- Evitar gradientes, animações excessivas e cores saturadas em grandes
  áreas.

## 2.4 Tema claro

Não é prioridade para o MVP. A arquitetura visual deve evitar cores
hardcoded nos widgets, permitindo adicionar um tema claro
posteriormente.

------------------------------------------------------------------------

# 3. Estrutura global da aplicação

A maioria das telas deve reutilizar o mesmo shell.

``` text
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ QA WORKBENCH                                           PROJ-001 / project-name              │
├───────────────────┬────────────────────────────────────────────────────┬─────────────────────┤
│ WORKSPACE         │ MAIN CONTENT                                       │ CONTEXT             │
│                   │                                                    │                     │
│ > Overview        │ Conteúdo do módulo selecionado                     │ Project             │
│   Requirements    │                                                    │ Environment         │
│   Test Cases      │ Listas, detalhes, formulários, logs ou preview     │ Branch              │
│   Test Plans      │                                                    │ AI Provider         │
│   Test Suites     │                                                    │ Recent activity     │
│                   │                                                    │                     │
│ EXECUTION         │                                                    │                     │
│   Test Execution  │                                                    │                     │
│   Browser Agent   │                                                    │                     │
│   Automation      │                                                    │                     │
│                   │                                                    │                     │
│ ANALYSIS          │                                                    │                     │
│   Issue Testing   │                                                    │                     │
│   Bug Hunting     │                                                    │                     │
│   Release Analysis│                                                    │                     │
│                   │                                                    │                     │
│ INTEGRATIONS      │                                                    │                     │
│   Pipelines       │                                                    │                     │
│   Issues          │                                                    │                     │
│   API Testing     │                                                    │                     │
│   Security        │                                                    │                     │
│                   │                                                    │                     │
│ SYSTEM            │                                                    │                     │
│   Reports         │                                                    │                     │
│   Knowledge       │                                                    │                     │
│   AI Agent        │                                                    │                     │
│   Settings        │                                                    │                     │
├───────────────────┴────────────────────────────────────────────────────┴─────────────────────┤
│ PROJ-001 │ staging │ OpenCode │ ● Ready │ Ctrl+B Browser │ ? Help                           │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Comportamento do shell

- Sidebar fixa em larguras de terminal adequadas.
- Painel contextual pode ser ocultado.
- Em terminais estreitos, reduzir a sidebar ou convertê-la em navegação
  por menu.
- A área central deve receber o espaço restante.
- A barra inferior deve mostrar projeto, ambiente, provider, estado e
  atalhos relevantes.
- Não duplicar no painel contextual informações já evidentes na área
  principal.
- A navegação deve funcionar sem mouse.

------------------------------------------------------------------------

# 4. Especificação das telas

## 4.1 Overview

**Objetivo:** resumir a situação de qualidade do projeto.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ OVERVIEW                                               PROJ-001              │
├──────────────────────────────────────────────────────────────────────────────┤
│ Project: project-name                    Branch: develop                     │
│ Repository: organization/repository      Environment: staging                │
│                                                                              │
│ QUALITY SUMMARY                                                             │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐          │
│ │ TEST CASES   │ │ PASSED       │ │ FAILED       │ │ BLOCKED      │          │
│ │     128      │ │     102      │ │      12      │ │       4      │          │
│ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘          │
│                                                                              │
│ RECENT EXECUTIONS                                                            │
│ EXEC-042  Login             ✓ PASSED       00:12                             │
│ EXEC-041  Cadastro          ✗ FAILED       00:34                             │
│ EXEC-040  Listagem          ✓ PASSED       00:18                             │
│                                                                              │
│ PIPELINES                                                                     │
│ PIPE-018  develop           ● RUNNING                                         │
│ PIPE-017  develop           ✗ FAILED                                          │
│                                                                              │
│ [New Test] [Run Suite] [Analyze Project] [Ask Agent]                         │
└──────────────────────────────────────────────────────────────────────────────┘
```

Elementos: - Identificação do projeto. - Indicadores derivados dos dados
persistidos. - Execuções recentes. - Pipelines recentes. - Ações
rápidas.

## 4.2 Requirements

**Objetivo:** consultar requisitos, critérios de aceitação e cobertura.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ REQUIREMENTS                                                24 REQUIREMENTS  │
├──────────────────────────────────────────────────────────────────────────────┤
│ Search: [................................................]                  │
│ [All] [Functional] [Non-functional] [Without Tests]                          │
│                                                                              │
│ ID        TITLE                         STATUS          COVERAGE             │
│ REQ-001   User authentication           Approved        100%                 │
│ REQ-002   Child registration             Approved         75%                 │
│ REQ-003   User management                Review           40%                 │
│                                                                              │
│ SELECTED: REQ-002                                                            │
│ Child registration                                                          │
│ Description: The system must allow registration with required data.         │
│                                                                              │
│ ACCEPTANCE CRITERIA                                                          │
│ [x] Name is required                                                        │
│ [x] Birth date must be valid                                                │
│ [ ] Duplicate registration is validated                                     │
│                                                                              │
│ RELATED TEST CASES                                                          │
│ TC-012  Valid registration                                                  │
│ TC-013  Registration without name                                           │
│                                                                              │
│ [Edit] [Generate Tests] [Analyze with AI]                                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 4.3 Test Cases

**Objetivo:** gerenciar casos de teste.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ TEST CASES                                                    128 CASES     │
├──────────────────────────────────────────────────────────────────────────────┤
│ [Search........................................] [ + New Test ]              │
│ [All] [Active] [Draft] [Archived]                                            │
│                                                                              │
│ ID        TITLE                         PRIORITY        STATUS               │
│ TC-001    Login with valid credentials  HIGH            ACTIVE               │
│ TC-002    Login with invalid password   HIGH            ACTIVE               │
│ TC-003    Child registration            HIGH            ACTIVE               │
│                                                                              │
│ SELECTED: TC-001                                                            │
│ Objective: Validate authentication with valid credentials.                 │
│ Requirement: REQ-001        Suite: SMOKE        Type: Functional             │
│                                                                              │
│ PRECONDITIONS                                                                │
│ - Application is available                                                  │
│ - Authorized test user exists                                               │
│                                                                              │
│ STEPS                                                                        │
│ 1. Open login page                                                           │
│ 2. Enter credentials                                                        │
│ 3. Click Sign in                                                             │
│                                                                              │
│ EXPECTED RESULT                                                              │
│ User is authenticated and redirected to the dashboard.                     │
│                                                                              │
│ [Edit] [Execute] [Duplicate] [AI Analysis]                                  │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 4.4 Test Planning

**Objetivo:** preparar campanha de testes.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ TEST PLANNING                                                               │
├──────────────────────────────────────────────────────────────────────────────┤
│ TEST PLAN: TP-001                 RELEASE: v1.5.0       STATUS: DRAFT         │
│                                                                              │
│ OBJECTIVE                                                                    │
│ Validate changed functionality before release.                              │
│                                                                              │
│ SCOPE                                                                        │
│ Included: Login, registration, user management                              │
│ Excluded: External integrations                                              │
│                                                                              │
│ STRATEGY                                                                     │
│ [x] Smoke   [x] Functional   [x] Regression   [ ] Security                   │
│                                                                              │
│ SELECTED SUITES                                                              │
│ Suite                    Tests                 Estimate                      │
│ Smoke                    12                    5 min                         │
│ Regression               45                    20 min                        │
│ API                      18                    8 min                         │
│                                                                              │
│ [Generate Plan] [Analyze Risk] [Approve] [Execute]                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 4.5 Test Suites

**Objetivo:** organizar casos de teste reutilizáveis.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ TEST SUITES                                                    12 SUITES    │
├──────────────────────────────────────────────────────────────────────────────┤
│ SUITES                    SELECTED: SMOKE                                    │
│ > SMOKE                   Essential application flows                       │
│   REGRESSION                                                                 │
│   E2E                                                                         │
│   API                                                                         │
│   SECURITY                                                                    │
│   CUSTOM                                                                      │
│                                                                              │
│ TEST CASES                                                                   │
│ [x] TC-001  Login with valid credentials                                     │
│ [x] TC-003  Child registration                                                │
│ [x] TC-008  Dashboard                                                         │
│ [x] TC-011  Listing                                                           │
│                                                                              │
│ Total: 4 tests       Last execution: EXEC-042       Result: PASSED            │
│                                                                              │
│ [Add Test] [Remove Test] [Run Suite] [Analyze Coverage]                     │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 4.6 Test Execution

**Objetivo:** acompanhar execução, etapas e evidências.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ TEST EXECUTION                                              EXEC-043        │
├──────────────────────────────────────────────────────────────────────────────┤
│ TC-001 — Login with valid credentials                                       │
│ Mode: AGENT-DRIVEN                Environment: STAGING                       │
│                                                                              │
│ ● RUNNING                                                                    │
│                                                                              │
│ EXECUTION STEPS                                                              │
│ [✓] 01 Open application                                                      │
│ [✓] 02 Open login page                                                       │
│ [✓] 03 Fill credentials                                                      │
│ [>] 04 Click Sign in                                                         │
│ [ ] 05 Validate dashboard                                                    │
│                                                                              │
│ CURRENT ACTION                                                               │
│ Playwright is clicking button "Sign in".                                    │
│                                                                              │
│ EVIDENCE                                                                      │
│ Screenshot: step-04.png       Browser events: 12       Requests: 8           │
│                                                                              │
│ [Pause] [Cancel] [Browser Preview] [View Logs]                              │
│                                                                              │
│ OUTPUT                                                                       │
│ 10:42:01 Navigation completed                                                │
│ 10:42:03 Login form detected                                                 │
│ 10:42:05 Credentials filled                                                  │
│ 10:42:06 Click action started                                                │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 4.7 Browser Preview

**Objetivo:** visualizar o Playwright trabalhando dentro da TUI.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ BROWSER PREVIEW                                  EXEC-043    ● RUNNING      │
├──────────────────────────────────────────────────────────────────────────────┤
│ URL: http://localhost:3000/login             MODE: PREVIEW                    │
│                                                                              │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │                                                                          │ │
│ │                           APPLICATION                                    │ │
│ │                                                                          │ │
│ │                              LOGIN                                       │ │
│ │                                                                          │ │
│ │                    ┌──────────────────────────┐                          │ │
│ │                    │ Email                    │                          │ │
│ │                    └──────────────────────────┘                          │ │
│ │                    ┌──────────────────────────┐                          │ │
│ │                    │ Password                 │                          │ │
│ │                    └──────────────────────────┘                          │ │
│ │                    ┌──────────────────────────┐                          │ │
│ │                    │          SIGN IN         │                          │ │
│ │                    └──────────────────────────┘                          │ │
│ │                                                                          │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ CURRENT ACTION: Clicking button "Sign in"                                   │
│ LAST SCREENSHOT: 10:42:06                                                   │
│                                                                              │
│ [Hide Preview] [Pause] [Stop] [Open External Browser]                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

Requisitos: - Preview baseado em screenshots atualizadas. - Não tentar
renderizar HTML interativo nativamente no terminal. - `Ctrl+B` mostra ou
oculta o painel. - Ocultar o preview não interrompe o teste. -
Evidências continuam sendo coletadas. - Ao reabrir, mostrar a imagem
mais recente. - Captura e renderização não podem bloquear a TUI. - Falha
de captura deve ser registrada separadamente da falha funcional. -
Modos: `headless`, `preview`, `visible`. - Trocar de headless para
visible pode exigir reiniciar o navegador e deve respeitar o ciclo da
execução.

## 4.8 Issue Testing

**Objetivo:** transformar issue em atividade de QA.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ ISSUE TESTING                                                    GITLAB     │
├──────────────────────────────────────────────────────────────────────────────┤
│ OPEN ISSUES                                                                  │
│ #340  Toast differs from registration requirement                           │
│ #341  Error saving form                                                      │
│ #342  User listing failure                                                   │
│                                                                              │
│ SELECTED ISSUE: #340                                                         │
│ Description: Message after registration differs from requirement.           │
│                                                                              │
│ AI ANALYSIS                                                                  │
│ Related requirement: REQ-002                                                 │
│ Existing tests: TC-003, TC-014                                               │
│ Risk: MEDIUM                                                                 │
│                                                                              │
│ PROPOSED TEST PLAN                                                           │
│ [x] Reproduce registration flow                                              │
│ [x] Validate toast                                                           │
│ [x] Compare with requirement                                                 │
│ [x] Capture screenshot                                                       │
│                                                                              │
│ [Analyze] [Generate Tests] [Execute] [Prepare Comment]                      │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 4.9 Bug Hunting

**Objetivo:** explorar e investigar possíveis defeitos.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ BUG HUNTING                                                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│ TARGET: http://localhost:3000              SESSION: BUG-019   ● RUNNING      │
│                                                                              │
│ OBSERVATIONS                                                                 │
│ 10:10:01 Page loaded                                                         │
│ 10:10:03 GET /api/users returned 200                                         │
│ 10:10:05 Registration button identified                                      │
│ 10:10:08 Console error detected                                              │
│                                                                              │
│ FINDINGS                                                                     │
│ ! SUSPECTED ISSUE                                                            │
│ TypeError: Cannot read properties of undefined                              │
│ Source: users.component.ts:82                                                │
│ Confidence: Medium                                                           │
│                                                                              │
│ EVIDENCE: 4 screenshots   1 console error   0 network failures               │
│                                                                              │
│ [Investigate] [Reproduce] [Create Bug] [Stop Session]                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 4.10 Release Analysis

**Objetivo:** analisar mudanças e recomendar regressão.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ RELEASE ANALYSIS                                                             │
├──────────────────────────────────────────────────────────────────────────────┤
│ BASE: main                         TARGET: develop                           │
│                                                                              │
│ CHANGES                                                                      │
│ Files changed: 18       Added: 5       Modified: 10       Deleted: 3          │
│                                                                              │
│ IMPACTED AREAS                                                               │
│ ! Authentication                                                             │
│ ! User management                                                            │
│   Reports                                                                    │
│                                                                              │
│ RECOMMENDED TESTS                                                            │
│ TC-001 Login                                                                 │
│ TC-003 Registration                                                         │
│ TC-008 Dashboard                                                             │
│ TC-021 Permissions                                                           │
│                                                                              │
│ RISK: HIGH                                                                   │
│                                                                              │
│ [Analyze Changes] [Generate Regression Suite] [Create Test Plan]            │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 4.11 Pipeline Management

**Objetivo:** consultar pipelines, stages e jobs.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ PIPELINE MANAGEMENT                                              GITLAB     │
├──────────────────────────────────────────────────────────────────────────────┤
│ RECENT PIPELINES                                                             │
│ PIPE-018  develop   ● RUNNING     02:10                                      │
│ PIPE-017  develop   ✗ FAILED      01:45                                      │
│ PIPE-016  main      ✓ SUCCESS     03:20                                      │
│                                                                              │
│ SELECTED: PIPE-017                                                           │
│                                                                              │
│ STAGES                                                                       │
│ validate       ✓ SUCCESS                                                     │
│ smoke          ✓ SUCCESS                                                     │
│ functional     ✗ FAILED                                                      │
│ integration    – SKIPPED                                                     │
│ e2e            – SKIPPED                                                     │
│                                                                              │
│ FAILED JOB: test-functional                                                  │
│ Exit code: 1                  Duration: 00:42                                │
│                                                                              │
│ [View Logs] [Analyze Failure] [View Artifacts] [Refresh]                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 4.12 Pipeline Analysis

**Objetivo:** identificar especificamente o que quebrou.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ PIPELINE ANALYSIS                                              PIPE-017     │
├──────────────────────────────────────────────────────────────────────────────┤
│ FAILURE SUMMARY                                                             │
│ Job: test-functional        Stage: functional        Status: FAILED          │
│                                                                              │
│ FAILED TESTS                                                                 │
│ TC-003 — Child registration                                                  │
│ TC-014 — Form validation                                                     │
│                                                                              │
│ ERROR                                                                        │
│ AssertionError                                                               │
│ Expected: "Registration successful"                                         │
│ Actual:   "Registration completed"                                           │
│                                                                              │
│ PROBABLE CAUSE                                                               │
│ Test expectation mismatch                                                   │
│ Confidence: HIGH                                                            │
│                                                                              │
│ RELATED: Issue #340       Requirement REQ-002                                │
│                                                                              │
│ [View Full Log] [Open Issue] [Prepare Comment]                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 4.13 Issue Management

**Objetivo:** revisar e publicar comentários com aprovação.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ ISSUE MANAGEMENT                                                            │
├──────────────────────────────────────────────────────────────────────────────┤
│ ISSUE #340                                                                   │
│ Toast differs from registration requirement                                  │
│                                                                              │
│ PROPOSED COMMENT                                                             │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ QA RESULT: FAILED                                                         │ │
│ │ Environment: staging                                                     │ │
│ │ Execution: EXEC-043                                                      │ │
│ │ Expected: "Registration successful"                                      │ │
│ │ Actual: "Registration completed"                                          │ │
│ │ Evidence: evidence/step-05.png                                            │ │
│ │ Conclusion: behavior differs from REQ-002.                               │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Provider: GitLab       Target: Issue #340       Status: Awaiting approval    │
│                                                                              │
│ [Edit Comment] [Approve & Publish] [Cancel]                                │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 4.14 API Testing

**Objetivo:** testar endpoints e validar contratos.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ API TESTING                                                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│ COLLECTIONS              REQUEST                                            │
│ > Authentication         [POST] /api/users                                   │
│   Users                                                                     │
│   Children                                                                  │
│   Reports                                                                   │
│                                                                              │
│ HEADERS                                                                      │
│ Content-Type: application/json                                               │
│ Authorization: Bearer ********                                               │
│                                                                              │
│ BODY                                                                        │
│ { "name": "Test User", "email": "test@example.com" }                         │
│                                                                              │
│ EXPECTED: Status 201       Schema: UserResponse                               │
│ RESULT:   Status 201 ✓ SUCCESS       Duration: 125 ms                        │
│                                                                              │
│ [Send] [Save Request] [Add Assertion] [View History]                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 4.15 Security

**Objetivo:** executar verificações de segurança autorizadas.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ SECURITY                                                                     │
├──────────────────────────────────────────────────────────────────────────────┤
│ TARGET: staging                    SCOPE: localhost:3000                     │
│ AUTHORIZATION: CONFIRMED                                                    │
│                                                                              │
│ SECURITY CHECKS                                                              │
│ [x] Authentication   [x] Authorization   [x] Session Management              │
│ [x] Input Validation [ ] API Security    [ ] Access Control                  │
│                                                                              │
│ FINDINGS                                                                     │
│ SEC-001  Missing authorization check            HIGH                        │
│ SEC-002  Sensitive data in response              MEDIUM                      │
│                                                                              │
│ POLICY                                                                       │
│ Rate limit: configured          Destructive tests: disabled                 │
│                                                                              │
│ [Start Scan] [Review Findings] [Generate Report]                            │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 4.16 Reports & Evidence

**Objetivo:** consultar relatórios e evidências.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ REPORTS & EVIDENCE                                                           │
├──────────────────────────────────────────────────────────────────────────────┤
│ REPORT TYPES                  RECENT REPORTS                                 │
│ > Execution Reports           REP-001  Smoke Test Report                     │
│   Defect Reports              REP-002  Regression Report                     │
│   Regression Reports          REP-003  Pipeline Failure Report               │
│   Pipeline Reports                                                           │
│   Security Reports                                                           │
│                                                                              │
│ EVIDENCE EXPLORER                                                            │
│ EXEC-043                                                                     │
│   screenshots/                                                               │
│   videos/                                                                    │
│   traces/                                                                    │
│   logs/                                                                      │
│   network/                                                                   │
│                                                                              │
│ [Open Report] [Export] [Browse Evidence]                                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 4.17 Knowledge Base

**Objetivo:** pesquisar o conhecimento persistido em Markdown.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ KNOWLEDGE BASE                                                               │
├──────────────────────────────────────────────────────────────────────────────┤
│ Search project knowledge: [........................................]        │
│                                                                              │
│ CATEGORIES                                                                   │
│ > Requirements                                                               │
│   Architecture                                                               │
│   Test Strategies                                                            │
│   Known Issues                                                               │
│   Execution History                                                          │
│   AI Knowledge                                                               │
│                                                                              │
│ RECENT DOCUMENTS                                                             │
│ README.md                                                                    │
│ authentication.md                                                            │
│ test-strategy.md                                                             │
│ known-issues.md                                                              │
│                                                                              │
│ Markdown: Source of truth        SQLite: Rebuildable index                   │
│                                                                              │
│ [Open Document] [Search] [Rebuild Index]                                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 4.18 AI Agent

**Objetivo:** conversar com o agente usando contexto do projeto.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ AI AGENT                                                   PROVIDER: OPENCODE│
├──────────────────────────────────────────────────────────────────────────────┤
│ CONTEXT: project-name / develop / staging                                   │
│                                                                              │
│ USER                                                                         │
│ Analyze issue #340 and prepare the required tests.                           │
│                                                                              │
│ QA AGENT                                                                     │
│ Requirement REQ-002 appears related to this issue.                           │
│ Existing test cases: TC-003 and TC-014.                                      │
│ I recommend executing both in staging and comparing the toast with REQ-002.  │
│                                                                              │
│ TOOLS                                                                        │
│ ✓ GitLab Issue Reader      ✓ Requirements Search                            │
│ ✓ Test Case Reader         ○ Playwright                                      │
│                                                                              │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ Ask the QA Agent...                                                       │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ [Send] [Attach Context] [Switch Provider]                                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 4.19 Settings

**Objetivo:** configurar aplicação, providers e integrações.

``` text
┌──────────────────────────────────────────────────────────────────────────────┐
│ SETTINGS                                                                     │
├──────────────────────────────────────────────────────────────────────────────┤
│ CATEGORIES                 GENERAL                                           │
│ > General                  Default project: project-name                    │
│   Appearance               Default environment: staging                     │
│   AI Providers             Default provider: OpenCode                       │
│   Browser                                                                    │
│   Integrations             BROWSER                                           │
│   Security                 Default mode: preview                             │
│   Storage                  Capture console: enabled                         │
│   Shortcuts                Capture network: enabled                         │
│                            Save traces: on failure                           │
│                                                                              │
│ [Save Changes] [Reset]                                                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

------------------------------------------------------------------------

# 5. Componentes visuais reutilizáveis

Implementar componentes compartilhados, em vez de recriar padrões em
cada tela:

- `AppShell`: estrutura global.
- `Sidebar`: navegação.
- `StatusBar`: projeto, ambiente, provider e estado.
- `PageHeader`: título, descrição e ações.
- `DataTable`: listagens.
- `FilterBar`: filtros e busca.
- `StatusIndicator`: estado com texto e símbolo.
- `MetricCard`: indicador numérico.
- `DetailPanel`: detalhes do item selecionado.
- `LogViewer`: logs com timestamp e nível.
- `ApprovalModal`: confirmação de ações sensíveis.
- `BrowserPreview`: visualização de screenshots.
- `EmptyState`: estado sem dados.
- `LoadingState`: carregamento.
- `ErrorState`: falha recuperável.
- `HelpBar`: atalhos contextuais.

Os componentes devem receber dados e callbacks; não devem conter regras
de negócio nem chamar integrações diretamente.

# 6. Navegação e atalhos

Atalhos iniciais sugeridos:

  Atalho                Ação
  --------------------- -----------------------------------------------------
  `Ctrl+P`              Abrir seletor de projeto ou ação, conforme contexto
  `Ctrl+B`              Mostrar/ocultar Browser Preview
  `Ctrl+Shift+B`        Solicitar mudança de modo do navegador
  `Ctrl+K`              Busca/command palette
  `Ctrl+L`              Focar campo de busca, quando disponível
  `Esc`                 Fechar modal ou voltar um nível
  `?`                   Ajuda contextual
  `Tab` / `Shift+Tab`   Navegar entre controles
  `Enter`               Ativar item focado

Os atalhos devem ser centralizados, documentados e configuráveis. Evitar
conflitos com atalhos padrão do terminal.

# 7. Responsividade do terminal

Definir comportamento por largura disponível, sem assumir que todos os
usuários têm terminais grandes.

- **Largo:** sidebar, conteúdo central e painel contextual.
- **Médio:** sidebar e conteúdo central; contexto em drawer ou aba.
- **Estreito:** navegação compacta e conteúdo em coluna única.
- **Altura reduzida:** esconder metadados secundários e permitir
  rolagem.

A aplicação deve detectar o espaço disponível por meio dos mecanismos do
Textual e reorganizar os widgets. Não fixar coordenadas absolutas para
todo o layout.

# 8. Requisitos de acessibilidade e legibilidade

- Contraste suficiente entre texto e fundo.
- Não usar cor como único indicador.
- Símbolos e rótulos para estados.
- Foco visível em todos os controles.
- Navegação integral por teclado.
- Não depender de animação.
- Mensagens de erro objetivas.
- Tabelas devem continuar legíveis em terminais estreitos.
- Logs longos devem ter rolagem e busca.

# 9. Orientação de implementação para o Codex

Antes de implementar telas, criar o tema e o shell global. Depois,
implementar componentes reutilizáveis e somente então os módulos.

Ordem sugerida:

1.  Tema dark e tokens semânticos de cor.
2.  AppShell, Sidebar e StatusBar.
3.  Navegação e command palette.
4.  Componentes comuns: tabela, filtros, indicadores, modais e logs.
5.  Overview.
6.  Requirements, Test Cases, Test Plans e Test Suites.
7.  Test Execution e Browser Preview.
8.  Demais módulos.
9.  Responsividade e acessibilidade.
10. Testes de interação da TUI.

Critérios de aceite visual: - Todas as telas compartilham a mesma
linguagem visual. - O estado selecionado e o foco são fáceis de
identificar. - A cor de status é consistente em toda a aplicação. - O
layout se adapta a diferentes dimensões de terminal. - O usuário
consegue navegar sem mouse. - A interface permanece responsiva durante
operações assíncronas. - Dados de exemplo não são apresentados como
dados reais do projeto. - A tela de execução e o Browser Preview não
bloqueiam o motor de testes. - O preview pode ser ocultado e reaberto
sem afetar a execução.

**Diretriz final:** priorizar uma TUI funcional, limpa e consistente. A
interface deve parecer uma ferramenta profissional de QA e
desenvolvimento, não um dashboard web comprimido dentro do terminal.
