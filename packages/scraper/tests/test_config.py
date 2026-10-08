def test_columns_verbatim():
    from legislative_scraper import config
    assert config.COLUMNS == ["Assembly","Session","Session_Date","DL_Category","Sr_No","Question_Number","Subject","Questions","Category","Departments","Ministry","Asked_By","Reply","Reply_Regional","Document_Link"]

def test_targets():
    from legislative_scraper import config
    from legislative_scraper.client import BASE_URL
    assert config.TARGET_ASSEMBLIES == {"11","10"}
    assert config.TARGET_SESSIONS == set()
    assert BASE_URL == "https://mgla.neva.gov.in"
