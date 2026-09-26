from backend.app.config import FALLBACK_DIR
from backend.app.data.symbols import parse_equity_csv, parse_index_csv, search_symbols
from backend.app.sentiment.analyze import score_headline


def test_shipped_equity_list_is_the_full_nse_file():
    rows = parse_equity_csv((FALLBACK_DIR / "EQUITY_L.csv").read_text(encoding="utf-8-sig"))
    assert len(rows) > 2000
    assert any(row["symbol"] == "RELIANCE" and "Reliance" in row["name"] for row in rows)
    assert all(row["series"] in {"EQ", "BE", "BZ"} for row in rows)


def test_nifty_lists_and_search_ranking():
    nifty100 = parse_index_csv((FALLBACK_DIR / "ind_nifty100list.csv").read_text(encoding="utf-8-sig"))
    nifty200 = parse_index_csv((FALLBACK_DIR / "ind_nifty200list.csv").read_text(encoding="utf-8-sig"))
    assert len(nifty100) >= 90
    assert len(nifty200) >= 180
    symbols = [
        {"symbol": "RELIANCE", "name": "Reliance Industries Limited"},
        {"symbol": "RELAXO", "name": "Relaxo Footwears Limited"},
        {"symbol": "TCS", "name": "Tata Consultancy Services Limited"},
    ]
    matches = search_symbols(symbols, "rel")
    assert [item["symbol"] for item in matches] == ["RELAXO", "RELIANCE"]
    assert search_symbols(symbols, "reliance")[0]["symbol"] == "RELIANCE"
    assert search_symbols(symbols, "tata")[0]["symbol"] == "TCS"


def test_finance_phrases_outrank_a_buried_word():
    assert score_headline("Company profit falls after a regulatory probe") < -0.2
    assert score_headline("Company profit jumps and beats estimates") > 0.4
    # "profit falls" must not be read as positive just because it contains "profit".
    assert score_headline("profit falls") < 0
