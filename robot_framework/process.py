"""This module contains the main process of the robot."""

import os
from datetime import date

from selenium import webdriver
from selenium.webdriver.common.by import By
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from itk_dev_shared_components.eflyt import eflyt_login, eflyt_search
from itk_dev_shared_components.eflyt.eflyt_case import Case

from robot_framework import config


def process(orchestrator_connection: OrchestratorConnection) -> None:
    """Do the primary process of the robot."""
    orchestrator_connection.log_trace("Running process.")
    eflyt_credentials = orchestrator_connection.get_credential(config.EFLYT_CREDS)
    browser = eflyt_login.login(eflyt_credentials.username, eflyt_credentials.password)

    eflyt_search.search(browser, to_date=date.today(), case_state="I gang")
    cases = eflyt_search.extract_cases(browser)
    cases = filter_cases(cases)
    for case in cases:
        eflyt_search.open_case(browser, case.case_number)
        handle_case(browser)


def filter_cases(cases: list[Case]) -> list[Case]:
    """Filter cases based on the assigned case worker.
    If the first two letters are EF, the case has received a reply on a lodging request.

    Args:
        cases: List of cases to filter.

    Returns:
        Filtered cases that needs to be checked further.
    """
    approved_case_types = [
        "Logivært",
        "Boligselskab"
    ]

    filtered_cases = []
    for case in cases:
        if case.case_worker[:2].upper() == "EF" and case.case_types in approved_case_types:
            filtered_cases.append(case)
    return filtered_cases


def handle_case(browser: webdriver.Chrome):
    """Check dates on each case, approve all cases where dates match.

    Args:
        browser: A selenium webdriver that has navigated to the case.
        case: A case that is currently open in the browser.
    """
    registered_date = browser.find_element(By.ID, "ctl00_ContentPlaceHolder2_GridViewMovingPersons_ctl02_lnkDateCPR").text
    browser.find_element(By.ID, "ctl00_ContentPlaceHolder2_ptFanePerson_moPersonTab_gvManuelOpfolgning_ctl05_lbtnVisSvar").click()
    response_date = browser.find_element(By.ID, "ctl00_ContentPlaceHolder2_ptFanePerson_moPersonTab_txtFradato")

    browser.find_element(By.ID, "ctl00_ContentPlaceHolder2_ptFanePerson_moPersonTab_btnLogivartResponseLuk").click()

    if registered_date == response_date:  # Approve the case
        deadline_field = browser.find_element(By.ID, "ctl00_ContentPlaceHolder2_ptFanePerson_ncPersonTab_txtDeadline")
        deadline_field.clear()
        note_field = browser.find_element(By.ID, "ctl00_ContentPlaceHolder2_ptFanePerson_ncPersonTab_txtDeadlineNote")
        note_field.clear()

        browser.find_element(By.ID, "ctl00_ContentPlaceHolder2_ptFanePerson_stcPersonTab1_btnGodkend").click()
        browser.find_element(By.ID, "ctl00_ContentPlaceHolder2_ptFanePerson_stcPersonTab1_btnApproveYes").click()

        person_table = browser.find_element(By.ID, "ctl00_ContentPlaceHolder2_GridViewMovingPersons")
        rows = person_table.find_elements(By.TAG_NAME, "tr")
        rows.pop(0)
        approve_persons_button = browser.find_element(By.ID, "ctl00_ContentPlaceHolder2_ptFanePerson_stcPersonTab1_btnGodkendAlle")

        if not approve_persons_button.is_enabled():
            for row in rows:
                row.find_element(By.XPATH, "td[2]").click()
                browser.find_element(By.ID, "ctl00_ContentPlaceHolder2_ptFanePerson_stcPersonTab1_btnGodkend").click()
                approve_button = browser.find_element(By.ID, "ctl00_ContentPlaceHolder2_ptFanePerson_stcPersonTab1_btnApproveYes")
                if approve_button.is_displayed():
                    approve_button.click()
        else:
            approve_persons_button.click()


if __name__ == '__main__':
    conn_string = os.getenv("OpenOrchestratorConnString")
    crypto_key = os.getenv("OpenOrchestratorKey")
    oc = OrchestratorConnection("Eflyt Test", conn_string, crypto_key, "")
    process(oc)
