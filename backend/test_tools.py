from tools import query_catalog, check_stock, reserve_item
import json

def test_query_catalog():
    result_str = query_catalog("headphones")
    result = json.loads(result_str)
    assert "results" in result
    assert len(result["results"]) > 0
    assert result["results"][0]["sku"] == "ELEC-001"
    assert result["results"][0]["price"] == 299.99

def test_query_catalog_not_found():
    result_str = query_catalog("spaceship")
    result = json.loads(result_str)
    assert "results" in result
    assert len(result["results"]) == 0

def test_check_stock():
    result_str = check_stock("APP-101")
    result = json.loads(result_str)
    assert result["sku"] == "APP-101"
    assert result["in_stock"] is True
    assert result["quantity"] > 0

def test_check_stock_out_of_stock():
    result_str = check_stock("HOME-050")
    result = json.loads(result_str)
    assert result["sku"] == "HOME-050"
    assert result["in_stock"] is False
    assert result["quantity"] == 0

def test_check_stock_invalid():
    result_str = check_stock("INVALID-SKU")
    result = json.loads(result_str)
    assert "error" in result

def test_reserve_item_success():
    result_str = reserve_item("ELEC-002", 2)
    result = json.loads(result_str)
    assert result["status"] == "reserved"
    assert result["sku"] == "ELEC-002"
    assert result["quantity"] == 2
    assert result["total_price"] == 149.50 * 2

def test_reserve_item_insufficient_stock():
    result_str = reserve_item("ELEC-002", 1000)
    result = json.loads(result_str)
    assert result["status"] == "failed"
    assert result["reason"] == "insufficient_stock"

def test_reserve_item_invalid():
    result_str = reserve_item("INVALID-SKU", 1)
    result = json.loads(result_str)
    assert "error" in result
