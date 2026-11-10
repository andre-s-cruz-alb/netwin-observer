# NETWIN Observer

Painel local de consulta para o NETWINUSA. Sem dependências Python externas e sem instalação nas VMs. Requer macOS, Python 3.9+ e OpenSSH (`python3 --version`, `ssh -V`). Se Python não existir, instale a distribuição oficial de python.org.

## Iniciar no Mac

1. Conecte à VPN/rede interna.
2. Extraia esta pasta. No Terminal, entre nela (`cd` seguido do caminho; pode arrastar a pasta ao Terminal).
3. Execute `sh connect.command`. Confirme a identidade SSH com a equipe e digite a senha no próprio Terminal. Mantenha essa sessão aberta. O app não recebe a senha. Se já usa chave/SSH Agent, essa etapa é opcional, mas a chave do host deve estar previamente verificada em known_hosts.
4. Em uma segunda janela, na mesma pasta: `sh start.command`.
5. Abra a URL completa exibida, incluindo `#token=...`. O token autentica apenas essa execução local e fica no sessionStorage da aba. Não compartilhe essa URL.
6. O painel consulta o backend DEV a cada 15 segundos enquanto a aba está visível. CPU precisa de duas consultas. Ctrl+C encerra o app; `exit` encerra a sessão SSH compartilhada.

Porta alternativa: `sh start.command --port 8766`.

## O que funciona

- Inventário DEV de backend, frontend, GeoServer, Oracle e Docmanager conforme a documentação consultada.
- CPU por diferença de /proc/stat, memória por /proc/meminfo, uso de disco raiz e uptime.
- Backend com as seis unidades systemd confirmadas; estado, subestado e MainPID. `active (exited)` é exibido como tal, sem declarar saúde do processo Java.
- Journal: últimas 150 linhas dos últimos 30 minutos, filtro local e atualização periódica. Logs em arquivo ainda não integrados. Sem sudo: journal restrito pode mostrar aviso ou conteúdo parcial. Nesse caso use o Terminal conforme as permissões existentes; o app não altera grupos ou sudoers.
- Métricas existentes via SSH: JBoss 8890, JVM 8891 ainda sem identificação funcional confirmada, exportador Nginx 9113. `nginx_up 0` é falha de coleta, não falha do Nginx. Não altera a configuração do exportador.
- Gráficos CPU/heap em memória no navegador, até 40 pontos. Sem armazenamento histórico permanente e sem alertas.
- Frontend, GeoServer e Docmanager descobrem serviços reais por SSH; endpoints de métricas adicionais precisam ser confirmados.

Nenhum dado exibido é simulado. Sem conexão, o painel informa falha/estado desconhecido e marca os dados anteriores como desatualizados.

## Mais hosts e ambientes

Edite `hosts.json` localmente e reinicie o app. Cada chave identifica um host. Campos: label, environment, hostname, address, user, services (nomes exatos systemd), metrics (nome -> porta local). A interface desta versão apresenta o inventário DEV; separação visual de vários ambientes é uma extensão futura. Para autenticar outro host, selecione-o e copie o comando da aba Acesso SSH. A senha do sistema operacional Oracle pode ser diferente das demais VMs.

## Limites e proteção

Servidor apenas em 127.0.0.1, com validação Host/Origin e token por execução. Não habilite encaminhamento público para o painel. Usa SSH com BatchMode e verificação estrita de host, sem shells locais para comandos remotos. Comandos remotos são consultas fixas, serviços e destinos vêm de configuração local confiável. A API não oferece execução arbitrária, edição, start/stop/restart ou sudo. O shell interativo de connect.command é o SSH habitual do usuário, fora da interface do app.

Consultas SSH têm timeout e limite de concorrência; falhas de VPN e autenticação são apresentadas. Não há confirmação funcional de endpoints de negócio, MongoDB, ZooKeeper ou Oracle. Métricas JVM não garantem que os serviços de negócio estejam saudáveis. Sem conexão a Prometheus/Grafana corporativo.

## Validação

`python3 -m unittest discover -s tests -v`

Os testes usam SSH simulado para parser, comandos permitidos e falhas. Não acessam as VMs. A validação real requer sua rede e autenticação.

O guia mencionado na conversa não estava disponível como anexo; esta implementação segue os requisitos descritos na conversa.

## Correção macOS

O socket SSH usa /tmp/nwo-<UID>/%C em diretório privado (700), evitando o limite de caminho de sockets Unix no macOS. Script e backend usam o mesmo caminho. Execute connect.command novamente e reinicie o app após atualizar. Para outro host: sh connect.command usuario@IP.

## Conectar várias máquinas DEV

Em terminais separados na pasta do app:

- `sh connect.command backend` → 10.112.100.140
- `sh connect.command frontend` → 10.112.100.141
- `sh connect.command geoserver` → 10.112.100.139

Mantenha cada sessão aberta. Um único `sh start.command` atende todos os hosts. Selecione a máquina na barra lateral. O botão Conectar SSH mostra o comando específico para copiar ao Terminal. O navegador não abre sessões SSH automaticamente nem pede senhas. Frontend, GeoServer e Docmanager descobrem unidades systemd relacionadas aos componentes; logs usam somente unidades encontradas nessa descoberta. CPU/memória/disco funcionam em todos os hosts com autenticação disponível. Endpoints de métricas de frontend/GeoServer ainda não foram confirmados e não são presumidos.

## Port forward pelo painel

1. Abra `sh connect.command backend` e mantenha a sessão autenticada aberta.
2. Inicie/reinicie o app e selecione Backend → Port forward.
3. Clique em Abrir túnel no serviço desejado. Para JBoss Debug, configure IntelliJ Remote JVM Debug, Attach, localhost, porta 18787.
4. Encerrar túnel remove apenas o encaminhamento criado pelo app; não fecha a sessão SSH nem reinicia a VM.

Destinos confirmados do backend: debug JBoss 8787→18787, métricas JBoss 8890→18890, segunda JVM 8891→18891, exportador Nginx 9113→19113 e status Nginx 3080→13080. Bind local sempre 127.0.0.1. Se um túnel manual já usa a porta, encerre-o antes. Não é possível descobrir antecipadamente se o destino remoto aceita a conexão apenas pela criação do túnel: o SSH encaminha a conexão quando o cliente a abre.

Frontend/GeoServer não recebem portas de debug presumidas. Adicione portas confirmadas no campo forwards do host em hosts.json (label, localPort, remotePort, kind; path opcional para HTTP). Reinicie o app após mudar configuração.

O controle usa `ssh -O forward/cancel` na sessão compartilhada existente. Não pede senhas pelo navegador. Fechar a aba do navegador não fecha os túneis: use Encerrar túnel ou Ctrl+C no servidor para encerrar os encaminhamentos que ele criou. Encerrar a sessão SSH também os remove. Se matar o processo do app de forma forçada, feche a sessão SSH para remover encaminhamentos remanescentes. Abrir debug permite que o IntelliJ suspenda threads: use com atenção no DEV compartilhado, preferindo Suspend: Thread.
