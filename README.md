# Sistema da equipe — Chess Challenge III (iCEV 2026)

Programa que decide os lances da equipe nas partidas presenciais do Chess Challenge III, no formato em que as equipes anunciam os lances em voz alta e o árbitro move as peças. Usa o **Stockfish 19** como motor de busca e acrescenta, por cima dele, uma camada própria de decisão:

- modelagem do adversário lance a lance;
- seleção adaptativa de lances;
- gestão de tempo para relógio físico sem acréscimo;
- livro de aberturas gerado pela equipe;
- tolerância a falhas e interface de operação.

O sistema roda **100% offline**, como exige o edital: nenhuma API externa, nenhum serviço online durante as partidas.

## Instalação (Windows)

O passo a passo completo para a equipe está em **`GUIA-DA-EQUIPE.md`**. O resumo:

1. Instale o Python 3.11 ou mais novo, marcando "Add Python to PATH".
2. Dê dois cliques em `1-instalar.bat`. Ele instala a dependência, baixa o Stockfish 19 para `engines/` e roda a verificação.
3. Dê dois cliques em `4-baixar-tablebases.bat` (cerca de 1 GB).
4. No notebook do torneio, dê dois cliques em `6-diagnostico.bat`. Ele mede a velocidade e o aquecimento e sugere threads e hash. Para gravar a sugestão: `python tools/diagnostico.py --aplicar`.
5. Dê dois cliques em `2-iniciar.bat`. O navegador abre em <http://127.0.0.1:8765>.

O mesmo pela linha de comando:

```
pip install -r requirements.txt
python tools/check_setup.py
python run.py
```

O Stockfish 19 fica em `engines/stockfish.exe`. O download é <https://github.com/official-stockfish/Stockfish/releases/tag/sf_19>.

## Preparação antes do torneio

**Gerar o livro de aberturas.** Ele é retomável: pode deixar rodando à noite, interromper com Ctrl+C e continuar depois.

```
python tools/build_book.py --plies 12 --our-time 30 --their-time 8 --branch 3
```

Nas posições em que é a nossa vez, o Stockfish analisa por 30 s e guarda o melhor lance. Nas posições do adversário, o livro ramifica nas 3 respostas mais fortes. Na partida, os lances de livro saem instantâneos e o relógio fica intacto.

**Medir a demora humana.** Esse é o ajuste que mais pesa. Em treinos com tabuleiro e relógio físicos, cronometrem dois tempos:

- `entry_lag_s`: do adversário apertar o relógio até o lance dele estar registrado no sistema;
- `exec_lag_s`: do nosso lance aparecer na tela até apertarmos o relógio.

Coloquem os valores medidos no `config.toml`. Sem acréscimo, cada segundo dessa demora se repete em todos os lances. Com 7 s por lance, uma partida passa de 15 minutos só de manuseio quando chega a 130 lances.

**Simular partidas completas.** Os comandos abaixo rodam partidas inteiras com relógio real e atrasos simulados:

```
python tools/simulate.py --opponent forte --games 4 --minutes 5 --lag 0.5
python tools/simulate.py --opponent fraco --games 2 --minutes 3
```

**Rodar os testes:** `python -m pytest -q`.

## Operação no dia (três pessoas)

Formato confirmado pela organização: as equipes ficam frente a frente, com o tabuleiro entre elas. Cada equipe anuncia o próprio lance em voz alta, e o árbitro escuta e move as peças.

| Função | O que faz |
|---|---|
| Operador | Escuta o anúncio do adversário e registra no sistema de uma de três formas: origem e destino (`g8f6`, `e7e8d`), por extenso (`cavalo de g8 para f6`, `roque pequeno`) ou arrastando a peça no tabuleiro. Se o adversário anunciar o lance que o sistema previu, basta um clique em "Ele anunciou o previsto". Em seguida, lê em voz alta o que ficou registrado. |
| Locutor | Anuncia o nosso lance lendo a frase em destaque, por exemplo "Cavalo de g1 para f3". |
| Conferente | Depois de cada movimento do árbitro, confere se o tabuleiro físico bate com a tela. As linhas "Confira:" mostram o que deve acontecer em capturas, roques, en passant e promoções. Também vigia os dois relógios e sincroniza o sistema com o relógio da mesa. |

**Protocolo de anúncio.** Sempre peça, casa de origem e casa de destino: "Cavalo de g1 para f3", "Peão de e4 captura em d5", "Roque pequeno", "Peão de e7 para e8, promove a dama".

A redundância é proposital. No barulho, "bê", "dê", "ê" e "gê" se confundem. Com origem e destino, um erro de audição quase sempre vira lance ilegal, que o sistema recusa na hora.

A entrada aceita três formas: origem e destino (`g8f6`), por extenso (`cavalo de g8 para f6`, `roque pequeno`) e arrastar a peça. Notação curta (`Cf6`, `Nf6`, `o-o`) é recusada, com sugestão do lance em coordenadas. A regra de segurança é única: o lance só é registrado se houver exatamente um lance legal correspondente; se houver mais de um, o sistema mostra as opções, e se não houver nenhum, explica o motivo. Enquanto o operador digita, a tela mostra o que será registrado.

**Combinar com o árbitro antes da primeira rodada:**

- quem aperta o relógio e em que momento (no anúncio ou depois de a peça ser movida);
- se ele aceita o anúncio com origem e destino;
- como pedir empate e como reivindicar repetição tripla ou a regra dos 50 lances.

Regras de operação:

- **Enquanto aparecer "Aguarde", ninguém anuncia nada.**
- **Lance do adversário registrado errado:** use "Corrigir lance do adversário" e registre o certo.
- **Oferta de empate:** clique em "Adversário ofereceu empate" e repita a decisão do software ao árbitro.
- **Reivindicar empate:** quando for vantajoso, a tela mostra o que dizer ao árbitro.
- **Nunca abandonar.** Software adversário pode travar ou estourar o tempo, e as duas coisas são derrota para eles.
- **Se o programa fechar:** abra de novo e clique em "Retomar partida salva". Depois sincronize os relógios.

Checklist antes de cada rodada:

- notebook na tomada e em modo de desempenho máximo;
- **modo avião**;
- suspensão e bloqueio de tela desligados;
- Windows Update pausado;
- base com cooler;
- `python tools/check_setup.py` rodado.

## O que é do Stockfish e o que é desta equipe

O **Stockfish 19** (GPLv3, <https://github.com/official-stockfish/Stockfish>) é usado sem alterações como motor de busca e avaliação. Ele fica num processo separado e conversa com o sistema pelo protocolo UCI. O binário não faz parte deste repositório.

Todo o código deste repositório é da equipe:

| Módulo | Função |
|---|---|
| `app/uci.py` | Cliente UCI próprio, com controle de tempo limite, encerramento forçado e leitura assíncrona. O Stockfish 19 encerra o processo diante de qualquer comando inválido, então todo lance é validado antes de ser enviado. |
| `app/engine.py` | Tolerância a falhas: reinício automático do motor, binário reserva e nova tentativa com tempo reduzido. |
| `app/emergency.py` | Busca alfa-beta mínima em Python, último recurso para nunca ficar sem lance. |
| `app/opponent.py` | Modelo do adversário. Estima a precisão dele pela variação da nossa expectativa de pontos após cada lance dele (mesma escala de precisão do Lichess). Mede também quanto ele joga o lance previsto e quanto tempo gasta. Classifica como forte, médio ou fraco. |
| `app/strategy.py` | Plano adaptativo com seis modos e seletor de lances sobre as linhas MultiPV. O lance escolhido nunca sai de uma margem de expectativa em relação ao melhor lance. |
| `app/clock.py` | Estimativa dos dois relógios físicos e cálculo do tempo de busca, reservando a demora humana dos lances restantes. |
| `app/controller.py` | Orquestração: livro, ponder (busca no tempo do adversário, com aproveitamento quando ele joga o lance previsto), adaptação, decisão sobre empates, salvamento e retomada. |
| `app/book.py` e `tools/build_book.py` | Livro de aberturas próprio, gerado com análise longa. |
| `app/static/index.html` e `app/server.py` | Interface de operação, sem dependências externas. |
| `tools/` e `tests/` | Simulador, verificação de ambiente e testes automatizados. |

Os seis modos do plano adaptativo:

| Modo | Quando entra | O que faz |
|---|---|---|
| Sólido | Padrão, e sempre contra adversário forte | Joga o melhor lance do motor. |
| Anti-empate | Posição igual contra adversário fraco ou médio | Evita repetições e trocas. |
| Pressão de relógio | O adversário tem bem menos tempo | Mantém o jogo vivo para o relógio dele correr. |
| Segurar o relógio | Posição igual e nós com menos tempo | Busca um empate reivindicável antes de o nosso relógio acabar. |
| Conversão | Já estamos ganhando | Joga o melhor lance, mais rápido. |
| Complicar | Estamos pior contra adversário falível | Escolhe linhas que dão mais chances de erro a ele. |

## Resultados de simulação

Rodados durante o desenvolvimento num ambiente de 1 núcleo, com partidas curtas (1,5 min por lado, atraso de 0,3 s por ponta).

| Adversário | Resultado | Perfil detectado | Observação |
|---|---|---|---|
| Stockfish nível 2 | Vitória por mate | — | Modo de conversão na maior parte da partida. |
| Stockfish nível 10 | Vitória por mate | Fraco (dois erros graves) | — |
| Stockfish completo, 1º teste | Derrota por tempo no lance 88 | Forte | O adversário da simulação não tinha demora humana. Esse resultado levou à criação do modo "Segurar o relógio" e da reivindicação automática de empate. |
| Stockfish completo, depois da correção | Vitória por tempo | Forte (72% de acerto da previsão) | Adversário com demora humana igual à nossa. O sistema usou o modo de pressão de relógio. |

São poucas partidas. Antes do torneio, rodem `tools/simulate.py` no notebook do torneio com mais jogos e tempos maiores.

## Configuração

Tudo fica em `config.toml`, com comentários. Os itens principais são:

- `engine.hash_mb`: 16384 neste notebook (16 GB dos 40). A placa de vídeo não calcula os lances;
- `engine.threads`: 12 neste i7-13650HX. Foi o ponto medido em que a velocidade ainda subia e sobrava CPU para o Windows;
- `clock.entry_lag_s` e `clock.exec_lag_s`: a demora medida em treino;
- `strategy.adaptive`: `false` desliga a adaptação e faz o sistema jogar sempre o melhor lance do motor.
