"""Entrada e saída de lances para os operadores.

Formato do torneio: as equipes anunciam os lances em voz alta e movem as peças no tabuleiro.

O operador registra o lance do adversário de TRÊS formas, e só delas:

  1. origem e destino:  g8f6, g8 f6, g8-f6, e7e8d (promoção: d, t, b, c)
  2. por extenso:       cavalo de g8 para f6, cavalo f6, peão captura em d5,
                        roque pequeno, peão de e7 para e8 promove a dama
  3. no tabuleiro:      arrastar a peça ou clicar na peça e depois no destino

Notação curta (Cf6, Nf6, exd5, o-o) é recusada de propósito, para a equipe usar um
único padrão. Nesses casos o sistema não registra nada, mas sugere o lance certo em
origem e destino.

Regra de segurança: só aceita se houver EXATAMENTE UM lance legal correspondente.
Se houver mais de um, mostra as opções; se não houver nenhum, explica por quê.

Saída (o que o locutor fala): frase com peça, origem e destino, por exemplo
"Cavalo de g1 para f3".
"""
from __future__ import annotations

import re
import unicodedata

import chess

PIECE_PT = {
    chess.PAWN: "Peão",
    chess.KNIGHT: "Cavalo",
    chess.BISHOP: "Bispo",
    chess.ROOK: "Torre",
    chess.QUEEN: "Dama",
    chess.KING: "Rei",
}
SAN_PT = {"K": "R", "Q": "D", "R": "T", "B": "B", "N": "C"}
PROMO_LETTERS = {"q": chess.QUEEN, "d": chess.QUEEN, "r": chess.ROOK, "t": chess.ROOK,
                 "b": chess.BISHOP, "n": chess.KNIGHT, "c": chess.KNIGHT}
PROMO_WORD_TYPES = {chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT}

_COORD = re.compile(r"^([a-h][1-8])([a-h][1-8])([qdrtbnc])?$")
_SQUARE = re.compile(r"[a-h][1-8]")

PIECE_WORDS = {"cavalo": chess.KNIGHT, "bispo": chess.BISHOP, "torre": chess.ROOK, "dama": chess.QUEEN,
               "rainha": chess.QUEEN, "rei": chess.KING, "peao": chess.PAWN}
FILLER_WORDS = {"de", "do", "da", "para", "pra", "pro", "em", "na", "no", "a", "o", "vai", "joga", "jogou",
                "casa", "ate", "en", "passant", "enpassant"}
CAPTURE_WORDS = {"captura", "capturando", "toma", "tomando", "come", "comendo", "x"}
CHECK_WORDS = {"xeque", "cheque", "mate", "xequemate"}
PROMO_WORDS = {"promove", "promocao", "promover", "promovendo", "vira", "coroa"}
SHORT_WORDS = {"pequeno", "curto", "menor"}
LONG_WORDS = {"grande", "longo", "maior"}
CASTLE_WORDS = {"roque"}
KNOWN_WORDS = (set(PIECE_WORDS) | FILLER_WORDS | CAPTURE_WORDS | CHECK_WORDS | PROMO_WORDS
               | SHORT_WORDS | LONG_WORDS | CASTLE_WORDS)
HOW = ("Digite origem e destino (ex.: g8f6), escreva por extenso (ex.: cavalo de g8 para f6) "
       "ou arraste a peça no tabuleiro.")


def _plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def coord_text(move: chess.Move) -> str:
    """Lance em origem e destino como o operador digita (promoção com letra portuguesa)."""
    text = chess.square_name(move.from_square) + chess.square_name(move.to_square)
    if move.promotion:
        text += {chess.QUEEN: "d", chess.ROOK: "t", chess.BISHOP: "b", chess.KNIGHT: "c"}[move.promotion]
    return text


def _say_list(board: chess.Board, moves) -> str:
    return "; ".join(f"{coord_text(m)} ({describe_move(board, m)['say']})" for m in moves)


def _check_note(board: chess.Board) -> str:
    return " O rei dele está em xeque: só valem lances que saem do xeque." if board.is_check() else ""


def _explain_square(board: chess.Board, dst: int, typed: str) -> ValueError:
    name = chess.square_name(dst)
    moves = [m for m in board.legal_moves if m.to_square == dst]
    if moves:
        return ValueError(f"'{typed}' não é legal nesta posição. Para {name} os lances legais são: "
                          f"{_say_list(board, moves[:6])}.{_check_note(board)}")
    return ValueError(f"'{typed}' não é legal: nenhuma peça do adversário pode ir para {name} nesta posição. "
                      f"Confira o tabuleiro e o lance anunciado.{_check_note(board)}")


def _castle(board: chess.Board, kind: str | None) -> chess.Move:
    options = []
    for move in board.legal_moves:
        if board.is_castling(move):
            kingside = chess.square_file(move.to_square) > chess.square_file(move.from_square)
            options.append(("pequeno" if kingside else "grande", move))
    if kind:
        for k, mv in options:
            if k == kind:
                return mv
        raise ValueError(f"Roque {kind} não é legal agora (rei ou torre já se moveram, casas ocupadas "
                         f"ou atacadas, ou rei em xeque).{_check_note(board)}")
    if len(options) == 1:
        return options[0][1]
    if not options:
        raise ValueError(f"Nenhum roque é legal agora.{_check_note(board)}")
    raise ValueError("Roque pequeno ou grande? Escreva 'roque pequeno' ou 'roque grande'.")


def _from_coords(board: chess.Board, src_name: str, dst_name: str, letter: str | None) -> chess.Move:
    src, dst = chess.parse_square(src_name), chess.parse_square(dst_name)
    candidates = [mv for mv in board.legal_moves if mv.from_square == src and mv.to_square == dst]
    if not candidates:
        piece = board.piece_at(src)
        if piece is None:
            raise ValueError(f"Não há peça em {src_name}. Confira o tabuleiro e a casa de origem anunciada.")
        if piece.color != board.turn:
            raise ValueError(f"A peça em {src_name} é nossa, não do adversário. Confira a casa de origem.")
        own = [m for m in board.legal_moves if m.from_square == src]
        name = PIECE_PT[piece.piece_type]
        if own:
            dests = ", ".join(sorted({chess.square_name(m.to_square) for m in own}))
            raise ValueError(f"{name} de {src_name} não pode ir para {dst_name}. "
                             f"Essa peça pode ir para: {dests}.{_check_note(board)}")
        raise ValueError(f"{name} de {src_name} não tem nenhum lance legal agora.{_check_note(board)}")
    if len(candidates) == 1 and candidates[0].promotion is None:
        return candidates[0]
    if not letter:
        raise ValueError(f"Promoção: informe a peça no fim: {src_name}{dst_name}d (Dama), t (Torre), "
                         "b (Bispo) ou c (Cavalo). Por extenso: 'promove a dama'.")
    wanted = PROMO_LETTERS[letter]
    for mv in candidates:
        if mv.promotion == wanted:
            return mv
    raise ValueError("Peça de promoção inválida.")


def _by_destination(board: chess.Board, core: str, piece: int | None, promo: int | None,
                    typed: str) -> chess.Move:
    """Extenso sem casa de origem: 'cavalo f6', 'peão captura d5', 'peão e8 promove dama'."""
    m = re.fullmatch(r"([a-h])?x?([a-h][1-8])", core)
    if not m:
        raise ValueError(f"Não entendi '{typed}'. {HOW}")
    file_hint, dst_name = m.group(1), m.group(2)
    if file_hint and piece not in (None, chess.PAWN):
        raise ValueError(f"Não entendi '{typed}'. {HOW}")
    dst = chess.parse_square(dst_name)
    moves = [mv for mv in board.legal_moves if mv.to_square == dst]
    if piece is not None:
        moves = [mv for mv in moves if board.piece_type_at(mv.from_square) == piece]
    if file_hint:
        moves = [mv for mv in moves if chess.square_file(mv.from_square) == "abcdefgh".index(file_hint)]
    if moves and all(mv.promotion for mv in moves):
        if promo is None:
            raise ValueError("Promoção: diga a peça, por exemplo 'peão e8 promove a dama'.")
        moves = [mv for mv in moves if mv.promotion == promo]
    if len(moves) == 1:
        return moves[0]
    if len(moves) > 1:
        raise ValueError(f"Mais de uma peça pode fazer '{typed}': {_say_list(board, moves[:6])}. "
                         "Diga também a casa de origem.")
    raise _explain_square(board, dst, typed)


def _parse_words(board: chess.Board, tokens: list[str], typed: str) -> chess.Move:
    piece: int | None = None
    promo: int | None = None
    core = ""
    promo_next = False
    castle: str | None = None
    for tok in tokens:
        if tok in PIECE_WORDS:
            if promo_next:
                promo = PIECE_WORDS[tok] if PIECE_WORDS[tok] in PROMO_WORD_TYPES else chess.QUEEN
                promo_next = False
            elif piece is None and not core:
                piece = PIECE_WORDS[tok]
            # outro nome de peça no meio (ex.: 'captura o bispo') é só descrição
        elif tok in CASTLE_WORDS:
            castle = castle or ""
        elif tok in SHORT_WORDS:
            castle = "pequeno"
        elif tok in LONG_WORDS:
            castle = "grande"
        elif tok in CAPTURE_WORDS:
            core += "x"
        elif tok in PROMO_WORDS:
            promo_next = True
        elif tok in FILLER_WORDS or tok in CHECK_WORDS:
            continue
        elif _SQUARE.fullmatch(tok) or re.fullmatch(r"[a-h]|x?[a-h][1-8]|[a-h][1-8][a-h][1-8]", tok):
            core += tok
        else:
            raise ValueError(f"Não entendi a palavra '{tok}' em '{typed}'. {HOW}")
    if castle is not None:
        return _castle(board, castle or None)

    squares = _SQUARE.findall(core)
    if len(squares) == 2:
        letter = None
        if promo is not None:
            letter = {chess.QUEEN: "d", chess.ROOK: "t", chess.BISHOP: "b", chess.KNIGHT: "c"}[promo]
        move = _from_coords(board, squares[0], squares[1], letter)
        if piece is not None and board.piece_type_at(move.from_square) != piece:
            actual = PIECE_PT[board.piece_type_at(move.from_square)].lower()
            raise ValueError(f"Em {squares[0]} há {actual}, não {PIECE_PT[piece].lower()}. Confira.")
        return move
    if len(squares) == 1:
        return _by_destination(board, core, piece, promo, typed)
    raise ValueError(f"Faltou a casa em '{typed}'. {HOW}")


def _suggest(board: chess.Board, compact: str) -> str:
    """Para notação curta recusada, sugere o lance em origem e destino (sem registrar)."""
    low = compact.lower().replace("0", "o").replace("-", "")
    if low.rstrip("+#") in ("oo", "ooo"):
        moves = [m for m in board.legal_moves if board.is_castling(m)
                 and (chess.square_file(m.to_square) > chess.square_file(m.from_square)) == (low.rstrip("+#") == "oo")]
    else:
        san = compact.rstrip("+#!?")
        variants = [san]
        if san and san[0].upper() in "RDTCBNQK" and len(san) >= 3:
            pt = {"R": ["K", "R"], "D": ["Q"], "T": ["R"], "C": ["N"], "B": ["B"], "N": ["N"], "Q": ["Q"], "K": ["K"]}
            variants = [en + san[1:] for en in pt[san[0].upper()]] + [san[0].lower() + san[1:]]
        elif san and san[0] in "AEFGH":
            variants = [san.lower()]
        found = {}
        for v in variants:
            v = re.sub(r"=?([DTCB])$", lambda mm: "=" + {"D": "Q", "T": "R", "C": "N", "B": "B"}[mm.group(1)], v)
            try:
                mv = board.parse_san(v)
                found[mv.uci()] = mv
            except chess.AmbiguousMoveError:
                dst = _SQUARE.findall(v)
                ptype = {"N": chess.KNIGHT, "B": chess.BISHOP, "R": chess.ROOK, "Q": chess.QUEEN, "K": chess.KING}.get(v[:1])
                if dst and ptype:
                    d = chess.parse_square(dst[-1])
                    for mv in board.legal_moves:
                        if mv.to_square == d and board.piece_type_at(mv.from_square) == ptype:
                            found[mv.uci()] = mv
            except ValueError:
                continue
        moves = list(found.values())
    if not moves:
        return ""
    return " Você quis dizer " + " ou ".join(f"{coord_text(m)} ({describe_move(board, m)['say']})" for m in moves[:3]) + "?"


def parse_move(board: chess.Board, text: str) -> chess.Move:
    typed = text.strip()
    if not typed:
        raise ValueError("Registre o lance do adversário. " + HOW)

    plain = _plain(typed)
    tokens = [t for t in re.split(r"[\s,;.!?]+", plain) if t]
    if any(t in KNOWN_WORDS and len(t) >= 3 for t in tokens):
        return _parse_words(board, tokens, typed)

    compact = typed.replace(" ", "")
    norm = compact.lower().replace("x", "").replace("-", "").replace("=", "").replace(":", "").rstrip("+#!?")
    m = _COORD.match(norm)
    if m:
        return _from_coords(board, m.group(1), m.group(2), m.group(3))

    raise ValueError(f"Formato não aceito: '{typed}'. {HOW}{_suggest(board, compact)}")


def san_pt(san: str) -> str:
    """Converte SAN inglesa para notação portuguesa (C, B, T, D, R)."""
    if san.startswith("O-O"):
        return san
    out = []
    for i, ch in enumerate(san):
        if ch in SAN_PT and (i == 0 or san[i - 1] == "="):
            out.append(SAN_PT[ch])
        else:
            out.append(ch)
    return "".join(out)


def describe_move(board: chess.Board, move: chess.Move) -> dict:
    """Descrição do lance. Chamar ANTES do push.

    say:   frase para anunciar em voz alta ao árbitro e ao adversário;
    text:  versão curta com seta (origem→destino);
    notes: o que o conferente deve ver acontecer no tabuleiro físico.
    """
    piece = board.piece_at(move.from_square)
    name = PIECE_PT[piece.piece_type] if piece else "Peça"
    src, dst = chess.square_name(move.from_square), chess.square_name(move.to_square)
    san = board.san(move)
    notes: list[str] = []
    if board.is_castling(move):
        kingside = chess.square_file(move.to_square) > chess.square_file(move.from_square)
        rank = "1" if piece.color == chess.WHITE else "8"
        rook_from, rook_to = ("h", "f") if kingside else ("a", "d")
        say = "Roque pequeno" if kingside else "Roque grande"
        text = f"{say}: Rei {src}→{dst}"
        notes.append(f"Mova o rei de {src} para {dst} e também a torre de {rook_from}{rank} para {rook_to}{rank}.")
    elif board.is_en_passant(move):
        cap_sq = chess.square_name(chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square)))
        say = f"Peão de {src} captura en passant em {dst}"
        text = f"Peão {src}→{dst} (en passant)"
        notes.append(f"Tire do tabuleiro o peão que está em {cap_sq}. Ele foi comido ao lado, não na casa de destino.")
    elif board.is_capture(move):
        captured = board.piece_at(move.to_square)
        say = f"{name} de {src} captura em {dst}"
        text = f"{name} {src}→{dst}"
        if captured:
            notes.append(f"Tire do tabuleiro a peça que estava em {dst}.")
    else:
        say = f"{name} de {src} para {dst}"
        text = f"{name} {src}→{dst}"
    if move.promotion:
        say += f", promove a {PIECE_PT[move.promotion].lower()}"
        notes.append(f"Troque o peão por uma {PIECE_PT[move.promotion].lower()}.")
    board.push(move)
    try:
        if board.is_checkmate():
            say += ", xeque-mate"
        elif board.is_check():
            say += ", xeque"
    finally:
        board.pop()
    return {"san": san, "san_pt": san_pt(san), "say": say, "text": text, "notes": notes, "from": src, "to": dst}
