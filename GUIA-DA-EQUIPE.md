# Guia da equipe — Chess Challenge III (iCEV 2026)

Este guia leva vocês da instalação até o dia do torneio. Leiam inteiro uma vez. Depois usem as seções como checklist.

**Datas que não podem passar:**

| Data | O quê |
|---|---|
| 03/11 | Último dia para inscrição ou mudança na equipe. |
| 04/11 | Envio do código via Git para icev@somosicev.com. Sem isso, a equipe é desclassificada. |
| 06/11 (sexta), a partir das 14h | Torneio presencial. |

---

## 1. Como funciona o torneio e o nosso sistema

As equipes sentam frente a frente, com o tabuleiro entre elas. Cada equipe **anuncia o próprio lance em voz alta**. O árbitro escuta e move as peças. Cada lado tem 25 minutos, sem acréscimo. Quem estoura o tempo perde. Software que trava também perde.

O nosso sistema roda no notebook, sem internet. Ele usa o Stockfish 19, o motor de xadrez mais forte que existe, e acrescenta uma camada que fizemos:

- **Livro de aberturas:** lances instantâneos no começo da partida.
- **Ponder:** o sistema pensa durante o tempo do adversário.
- **Adaptação ao adversário:** classifica o adversário como forte, médio ou fraco e muda o estilo de jogo.
- **Gestão de tempo:** calculada para o relógio físico.
- **Recuperação automática de falhas:** se o motor ou o programa cair, o sistema se recupera sozinho.

---

## 2. Instalação (Windows, uns 10 minutos)

### 2.1 Pré-requisitos

1. **Python 3.11 ou mais novo.**
   - Para conferir, abra o PowerShell e digite `python --version`.
   - Se não tiver, baixe em <https://www.python.org/downloads/>.
   - No instalador, **marque "Add Python to PATH"**.
2. **Uns 2 GB livres em disco**, contando as tablebases.
3. **Internet**, só para a instalação.

### 2.2 Instalação automática (recomendada)

1. **Extraia o zip.** Clique com o botão direito em **Extrair tudo**.
2. **Abra a pasta extraída.** Ela tem que mostrar `run.py`, `config.toml` e os arquivos `.bat`.
3. **Dê dois cliques em `1-instalar.bat`.** Ele faz três coisas:
   - instala a biblioteca de xadrez;
   - baixa o Stockfish 19 para a pasta `engines`;
   - roda a verificação.
4. **Se o Windows mostrar "O Windows protegeu o computador",** clique em **Mais informações** e depois em **Executar assim mesmo**.
5. **Leia o resultado da verificação no fim:**
   - não pode aparecer **FALHA**;
   - avisos de tablebases, livro e internet são normais nesse momento.
6. **Dê dois cliques em `4-baixar-tablebases.bat`.** Ele baixa cerca de 1 GB. Esses arquivos fazem os finais de partida saírem perfeitos.

### 2.3 Instalação manual (se o .bat falhar)

Abra o PowerShell **na pasta que tem o `run.py`**. Para isso, clique na barra de endereço do Explorer, digite `powershell` e aperte Enter. Depois rode **um comando de cada vez**:

```
pip install -r requirements.txt
```

```
Invoke-WebRequest https://github.com/official-stockfish/Stockfish/releases/download/sf_19/stockfish-windows-x86-64-universal.zip -OutFile sf.zip
```

```
Expand-Archive sf.zip -DestinationPath sf -Force
```

```
Get-ChildItem sf -Recurse -Filter *.exe | Select-Object -First 1 | Copy-Item -Destination engines\stockfish.exe
```

```
Copy-Item engines\stockfish.exe engines\stockfish-reserva.exe
```

```
python tools\check_setup.py
```

### 2.4 Abrindo o sistema

Dê dois cliques em **`2-iniciar.bat`**. O navegador abre em <http://127.0.0.1:8765>. Se não abrir, digite esse endereço no navegador.

A janela preta precisa ficar aberta: fechar ela fecha o sistema.

### 2.5 Atalhos e comandos equivalentes

Todo atalho `.bat` tem um comando equivalente. Os comandos rodam no PowerShell aberto na pasta do `run.py`.

| Atalho (dois cliques) | Comando no PowerShell | Para que serve |
|---|---|---|
| `1-instalar.bat` | ver seção 2.3 | Instala tudo. |
| `2-iniciar.bat` | `python run.py` | Abre o sistema. |
| `3-verificar.bat` | `python tools\check_setup.py` | Checagem antes de cada rodada. |
| `4-baixar-tablebases.bat` | `python tools\download_syzygy.py` | Baixa os finais perfeitos (1 GB). |
| `5-gerar-livro.bat` | `python tools\build_book.py --plies 12 --our-time 30 --their-time 8 --branch 3` | Gera o livro de aberturas (horas). |
| `6-diagnostico.bat` | `python tools\diagnostico.py` | Mede o notebook e sugere a configuração. |
| — | `python tools\diagnostico.py --aplicar` | Mede e já grava a sugestão no `config.toml`. |
| — | `python -m pytest -q` | Roda os testes automatizados. |

---

## 3. Adaptar ao notebook do torneio (obrigatório)

Cada notebook tem processador, memória e refrigeração diferentes. A configuração precisa ser ajustada para **o notebook que vai para a mesa na sexta**. Façam isso nele, do jeito que ele vai estar no torneio:

- na tomada;
- em **Configurações > Sistema > Energia > Melhor desempenho**;
- com todos os outros programas fechados.

### 3.1 Rodar o diagnóstico

Dê dois cliques em `6-diagnostico.bat`, ou rode:

```
python tools\diagnostico.py
```

Ele leva cerca de 1 minuto e faz três medições:

- a velocidade do motor com diferentes números de threads;
- se o notebook perde velocidade ao esquentar (3 rodadas de 10 segundos);
- quanto tempo leva para reservar a memória do motor.

No fim, aparece um bloco assim:

```
===== COPIE DAQUI =====
Data: ...
CPU: ... | ... núcleos físicos | ... lógicos
RAM: ... GB total | ... GB livre agora
Energia: na tomada, plano ...
Velocidade: ... threads: ... M/s | ...
Sustentado (...): ... M/s (queda ...%)
Sugestão: threads = ..., hash_mb = ...
ALERTA: ...            (só aparece se houver problema)
===== ATÉ AQUI =====
```

### 3.2 O que mandar de volta

**Copiem o bloco inteiro, de "COPIE DAQUI" até "ATÉ AQUI", e mandem para o Gabriel.** O mesmo texto fica salvo em `saves\diagnostico.txt`.

Se aparecer alguma linha **ALERTA**, resolvam antes de seguir:

| Alerta | O que fazer |
|---|---|
| Na bateria | Ligue na tomada e rode o diagnóstico de novo. |
| Queda de velocidade (aquecimento) | Use base com cooler e deixe as saídas de ar livres. |
| Pouca RAM livre | Feche os outros programas. |
| Velocidade baixa | Confira o modo de energia e os programas abertos. |

### 3.3 Aplicar a sugestão

Para gravar a sugestão no `config.toml`, rode:

```
python tools\diagnostico.py --aplicar
```

O comando grava `threads`, `hash_mb` e `high_priority = false`. Depois rode `3-verificar.bat` para conferir.

---

## 4. A tela

| Área | O que mostra |
|---|---|
| Tabuleiro (esquerda) | A posição atual, sempre com a nossa cor embaixo. O amarelo marca o nosso último lance e o azul, o do adversário. |
| Campo de lance (abaixo do tabuleiro) | Onde o operador registra o lance do adversário. Embaixo dele aparecem o botão **"Ele anunciou o previsto"** e a confirmação do que foi registrado. |
| Painel principal (direita, topo) | Tem dois estados. **"Aguarde"**: o motor está pensando, e ninguém anuncia nada. **Amarelo com "Anuncie"**: a frase que o locutor lê em voz alta, por exemplo "Cavalo de g1 para f3". As linhas **"Confira:"** dizem o que o conferente deve ver no tabuleiro. |
| Relógios | Estimativa dos dois relógios. A borda marca de quem é a vez. O número fica vermelho abaixo de 2 minutos. |
| Botões | "Jogar agora", "Corrigir lance do adversário", "Adversário ofereceu empate" e "Sincronizar" (para acertar com o relógio da mesa). |
| Adversário | O perfil detectado (forte, médio ou fraco), a precisão e o modo de jogo atual. |
| Motor | Avaliação, profundidade, velocidade e reinícios. |
| Súmula | Os lances da partida em notação portuguesa. |
| "Partida e registro" (fim da página) | Nova partida, registrar resultado, voz sintética e o log do sistema. |

---

## 5. Papéis e protocolo

| Papel | Responsabilidade |
|---|---|
| **Operador** | Escuta o adversário e registra o lance. Depois **lê em voz alta o que ficou registrado**, para o árbitro e a outra equipe confirmarem. |
| **Locutor** | Lê a frase do painel amarelo, devagar e claro. Só anuncia quando o painel estiver amarelo. |
| **Conferente** | Depois de cada movimento do árbitro, confere se o tabuleiro físico bate com a tela. Vigia os dois relógios e sincroniza se a diferença passar de uns 10 segundos. |

**Anúncio sempre com peça, origem e destino.** "Bê", "dê", "ê" e "gê" se confundem no barulho. Com origem e destino, um erro de audição quase sempre vira lance ilegal, e o sistema recusa na hora.

### Como o operador registra o lance

O sistema aceita **três formas**, e só elas:

| Forma | Exemplos |
|---|---|
| **1. Origem e destino** (a mais rápida) | `g8f6` · `e7e5` · `e4d5` (captura) · `e1g1` (roque pequeno) · `e7e8d` (promove a dama) |
| **2. Por extenso** | `cavalo de g8 para f6` · `cavalo f6` · `peão captura em d5` · `roque pequeno` · `peão de e7 para e8 promove a dama` |
| **3. No tabuleiro** | Arraste a peça do adversário até a casa de destino, ou clique na peça e depois no destino |

Detalhes de cada caso:

- **Promoção em origem e destino:** coloque a letra da peça no fim. d = Dama, t = Torre, b = Bispo, c = Cavalo. No tabuleiro, aparece um menu para escolher a peça.
- **Roque em origem e destino:** é a casa do rei. Pequeno das brancas: `e1g1`. Grande das brancas: `e1c1`. Pretas: `e8g8` e `e8c8`. Por extenso: `roque pequeno` ou `roque grande`.
- **Por extenso sem a casa de origem** (`cavalo f6`): só funciona se uma única peça daquele tipo puder ir para lá. Se houver duas, o sistema pede a origem.
- **Notação curta** (`Cf6`, `Nf6`, `e5`, `exd5`, `o-o`) **não é aceita**. O sistema recusa e sugere o lance certo, por exemplo: "Você quis dizer g8f6 (Cavalo de g8 para f6)?".

**Antes de apertar Enter, olhem a linha verde embaixo do campo.** Ela mostra exatamente o que vai ser registrado, por exemplo "Enter registra: Cavalo de g8 para f6 (g8f6)". Se a linha não ficar verde, o texto explica o problema.

Quando o sistema recusa, ele diz por quê:

| Situação | Exemplo | O que o sistema responde |
|---|---|---|
| Peça não pode ir para a casa | `g8f5` | "Cavalo de g8 não pode ir para f5. Essa peça pode ir para: f6, h6." |
| Não há peça na origem | `e2e4` com e2 vazia | "Não há peça em e2." |
| A peça é nossa | origem com peça da nossa cor | "A peça em e2 é nossa, não do adversário." |
| Duas peças iguais podem ir | `cavalo e4` com dois cavalos | Mostra os dois e pede a origem, por exemplo `c3e4` ou `g3e4`. |
| Promoção sem a peça | `e7e8` | Pede a letra: `e7e8d`, `e7e8t`, `e7e8b` ou `e7e8c`. |
| Rei em xeque | lance que não sai do xeque | Avisa que só valem lances que saem do xeque. |
| Notação curta | `Cf6` | Recusa e sugere `g8f6`. |

**Lance registrado errado:** clique em **Corrigir lance do adversário** e registre de novo.

---

## 6. Roteiro de testes (hoje à noite)

### 6.1 Preparação

- [ ] Notebook na tomada, em modo de energia **Melhor desempenho**, com a suspensão em "Nunca" na tomada.
- [ ] Programas pesados fechados: IDE, Docker, navegador com muitas abas.
- [ ] Instalação feita, com `4-baixar-tablebases.bat` rodado.
- [ ] Diagnóstico da seção 3 rodado e sugestão aplicada (`python tools\diagnostico.py --aplicar`).
- [ ] Tabuleiro físico, relógio de xadrez (um app de relógio no celular serve; 25 minutos sem acréscimo) e um segundo celular com cronômetro.
- [ ] Adversário de treino. O ideal é outro notebook rodando o mesmo sistema, como na sexta. Se não der, alguém tira os lances de um app de xadrez contra o motor.

### 6.2 Teste do fluxo (30 min)

1. **Abra com `2-iniciar.bat`.** Escolha **Pretas**, clique em **Começar** e digite `e2e4`.
   - **Esperado:** "Registrado: Peão de e2 para e4", depois "Aguarde" por alguns segundos, depois o painel amarelo com o nosso lance.
2. **Partida de 10 minutos para pegar o ritmo,** com os papéis da seção 5.
3. **Lances especiais.** Em **Nova partida**, escolha **Pretas** e cole a posição no campo FEN:

   | Situação | FEN | Digitar |
   |---|---|---|
   | Promoção | `8/4P3/8/8/8/8/k7/4K3 w - - 0 1` | `e7e8d` ou arrastar o peão |
   | Roque | `r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1` | `e1g1` ou `roque pequeno` |
   | En passant | `4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1` | `e5d6` |

4. **Erros de propósito:**
   - **Lance ilegal** (`e2e5` numa posição em que ele não existe): a mensagem tem que explicar o erro.
   - **As três formas para o mesmo lance:** digitar `g1f3`, escrever `cavalo de g1 para f3` e arrastar o cavalo. A linha verde (ou o registro) tem que mostrar o mesmo lance nas três.
   - **Notação curta** (`Cf3`): tem que ser recusada com a sugestão `g1f3`.
   - **Dois cavalos para a mesma casa:** a mensagem tem que pedir a origem.
   - **Lance errado registrado:** registre e use **Corrigir lance do adversário**.
5. **Empate:** clique em **Adversário ofereceu empate** e leia a decisão do software.

**Resultado esperado: tudo funciona sem travar a tela.**

### 6.3 Ensaio geral de 25 minutos (60 min)

1. **Ative o modo avião** e rode `3-verificar.bat`. O aviso de internet tem que sumir.
2. **Joguem uma partida completa, 25 minutos sem acréscimo**, exatamente como na sexta.
3. **Meçam com o cronômetro, em uns 10 lances, e anotem a média:**
   - **A (entry_lag):** do adversário terminar o anúncio até o lance estar registrado;
   - **B (exec_lag):** do nosso lance aparecer no painel amarelo até o relógio ser apertado.
4. **Nos lances 20 e 40,** anotem os relógios da tela e os da mesa.
5. **No meio da partida, ensaiem as falhas:**
   - **Motor morto:** Ctrl+Shift+Esc, encerre o `stockfish.exe`. O sistema tem que seguir sozinho e o contador "Reinícios" tem que subir para 1.
   - **Programa fechado:** feche a janela preta e abra `2-iniciar.bat` de novo. Clique em **Retomar partida salva** e depois em **Sincronizar** com o tempo da mesa.

**Folha de medição:**

| Lance | A: registro (s) | B: execução (s) |
|---|---|---|
| 1 | | |
| 2 | | |
| … | | |
| Média | | |

| Momento | Relógio nosso (tela / mesa) | Relógio deles (tela / mesa) |
|---|---|---|
| Lance 20 | | |
| Lance 40 | | |

### 6.4 Depois do ensaio

1. **Abra o `config.toml` no Bloco de Notas** e troque `entry_lag_s` e `exec_lag_s` pelas médias A e B.
2. **Se a máquina travou,** reduza `threads`, por exemplo para metade dos núcleos, e `hash_mb` (por exemplo `4096`). Depois rode `python tools\diagnostico.py` de novo.
3. **Gere o livro de aberturas de madrugada.**
   - Feche o sistema e dê dois cliques em `5-gerar-livro.bat`.
   - Deixe o notebook na tomada, sem suspensão.
   - Pode levar várias horas. Se parar, rode de novo: ele continua de onde parou.

### 6.5 O que mandar de volta depois do teste

Mandem tudo para o Gabriel, para ele ajustar o sistema antes do envio:

1. **O bloco do diagnóstico** (seção 3.2), rodado no notebook do torneio.
2. **As médias A e B** da folha de medição.
3. **A comparação dos relógios** nos lances 20 e 40, tela contra mesa.
4. **O que travou, confundiu ou demorou**, nas palavras de vocês.
5. **Se algo deu erro:** a mensagem da janela preta e o arquivo `saves\log.txt`.

---

## 7. Envio para a faculdade (até 04/11)

O edital exige o código **via Git**, enviado para **icev@somosicev.com**. Sem envio, ou com código não validado, a equipe é desclassificada.

### 7.1 Criar o repositório (uma pessoa faz)

1. **No GitHub,** crie um repositório chamado `chess-challenge-icev`, sem README.
2. **Na pasta do projeto,** abra o PowerShell e rode, trocando `SEU_USUARIO`:

   ```
   git init
   git add .
   git commit -m "Sistema da equipe para o Chess Challenge III"
   git branch -M main
   git remote add origin https://github.com/SEU_USUARIO/chess-challenge-icev.git
   git push -u origin main
   ```

   O `.gitignore` já deixa de fora o executável do Stockfish, as tablebases e os salvamentos.
3. **Adicione os outros dois integrantes** em **Settings > Collaborators**.
4. **Se o repositório for privado,** adicione também quem vai avaliar, ou deixe público. Confirmem com a organização qual opção preferem.

### 7.2 Atualizar depois de mudanças

Depois do ensaio (config ajustado) e quando o livro terminar:

```
git add .
git commit -m "Ajuste dos tempos medidos no ensaio e livro de aberturas"
git push
```

Façam commits pequenos e frequentes. O histórico mostra à banca o trabalho da equipe, e o edital pede **"modificações significativas"**.

### 7.3 E-mail de envio

Mandem do e-mail institucional.

> **Para:** icev@somosicev.com
> **Assunto:** Chess Challenge III — envio do código — Equipe [NOME DA EQUIPE]
>
> Prezados,
>
> Segue o repositório Git do software da equipe [NOME DA EQUIPE] para o Chess Challenge III:
> [LINK DO REPOSITÓRIO]
>
> Integrantes: [NOME 1] (iCEV), [NOME 2], [NOME 3].
>
> O sistema usa o Stockfish 19 (GPLv3) como motor de busca. O código do repositório é da equipe: camada de decisão adaptativa com modelo do adversário, gestão de tempo para relógio físico, livro de aberturas próprio, ponder, tolerância a falhas e interface de operação. O README detalha o que é do Stockfish e o que desenvolvemos, e como executar.
>
> O software roda totalmente offline, sem comunicação externa durante as partidas.
>
> Ficamos à disposição para apresentar o código.
>
> Atenciosamente,
> [NOME] — equipe [NOME DA EQUIPE]

Aproveitem o mesmo e-mail, ou mandem outro para coordenacao.engsoftware@somosicev.com, com as dúvidas da seção 9.

---

## 8. Dia do torneio (sexta, 06/11)

### Quinta à noite

- [ ] `git pull` no notebook do torneio. A versão que vai rodar tem que ser a do repositório.
- [ ] Rodar `6-diagnostico.bat` mais uma vez e conferir se não há ALERTA.
- [ ] Rodar `3-verificar.bat`.
- [ ] Carregadores, mouse e cooler separados.

### Antes de sair de casa e antes de cada rodada

- [ ] Notebook na tomada, em **Melhor desempenho**, com a suspensão desligada e o Windows Update pausado.
- [ ] **Modo avião.**
- [ ] Só o sistema aberto. Rodar `3-verificar.bat`: nenhuma FALHA e nenhum aviso de internet.
- [ ] Abrir com `2-iniciar.bat`. Em **Nova partida**, escolher a cor e clicar em **Começar** junto com o relógio.

### Durante a partida

- Enquanto aparecer **"Aguarde"**, ninguém anuncia nada.
- **Nunca abandonar.** O software adversário pode travar ou estourar o tempo.
- Se a tela mandar **reivindicar empate** ou disser o que fazer numa oferta de empate, repitam ao árbitro.
- **Se algo der errado:**
  - lance errado: **Corrigir lance do adversário**;
  - programa fechou: `2-iniciar.bat` e **Retomar partida salva**;
  - relógio diferente do da mesa: **Sincronizar**.

### Depois de cada partida

- Em "Partida e registro", **registrem o resultado** se a partida terminou fora do tabuleiro (tempo, árbitro). As partidas ficam salvas em `saves\partidas`.

---

## 9. Combinar com o árbitro ou a organização

1. **Quem aperta o relógio e em que momento:** no anúncio ou depois de a peça ser movida? Isso muda os tempos A e B do `config.toml`.
2. **O anúncio com peça, origem e destino é aceito?**
3. **Como pedir empate e como reivindicar repetição tripla ou a regra dos 50 lances.**
4. **No mata-mata, como se resolve empate?** O edital não diz.
5. **O edital fala em 8 equipes nas fases finais, mas a notícia fala em oitavas.** Qual vale?
6. **O local:** Espaço Cev Kennedy (edital) ou Espaço Piauhy (notícia)?

---

## 10. Problemas comuns

| Problema | Solução |
|---|---|
| "python não é reconhecido" | Reinstale o Python marcando "Add Python to PATH". Ou use `py` no lugar de `python`. |
| "Could not open requirements file" | Você está na pasta errada. Entre na pasta que tem o `run.py`. |
| "Motor não encontrado" | Falta o `engines\stockfish.exe`. Rode `1-instalar.bat` ou a instalação manual. |
| O Windows bloqueia o `.bat` ou o `.exe` | Mais informações e depois Executar assim mesmo. |
| A máquina trava com RAM livre | Não passe de `threads = 12` nem ligue `high_priority`. Hash de 16384 MB cabe nos 40 GB. Feche e abra de novo. |
| O navegador não abre | Abra <http://127.0.0.1:8765> manualmente. |
| "Address already in use" | O sistema já está aberto em outra janela, ou a porta está ocupada. Feche a outra janela ou troque `port` no `config.toml`. |
| O relógio da tela diverge do da mesa | Use Sincronizar e ajuste `entry_lag_s` e `exec_lag_s` com os tempos medidos. |
| O sistema mostra "Reiniciando motor" | É normal: ele se recuperou de uma falha. Se acontecer várias vezes, avise. |

**Detalhes técnicos:** `README.md`. **Registro de tudo o que aconteceu:** `saves\log.txt`.
