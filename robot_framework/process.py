"""This module contains the main process of the robot."""

import os
from datetime import date

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection, QueueStatus
from itk_dev_shared_components.eflyt import eflyt_login, eflyt_search, eflyt_case
from itk_dev_shared_components.eflyt.eflyt_case import Case
import itk_dev_event_log

from robot_framework import config


def process(orchestrator_connection: OrchestratorConnection) -> None:
    """Do the primary process of the robot."""
    orchestrator_connection.log_trace("Running process.")

    event_log = orchestrator_connection.get_constant("Event Log")
    itk_dev_event_log.setup_logging(event_log.value)

    eflyt_credentials = orchestrator_connection.get_credential(config.EFLYT_CREDS)
    browser = eflyt_login.login(eflyt_credentials.username, eflyt_credentials.password)

    eflyt_search.search(browser, to_date=date.today(), case_state="I gang")
    cases = eflyt_search.extract_cases(browser)
    cases = filter_cases(cases)
    for case in cases:
        queue_element = orchestrator_connection.create_queue_element(config.QUEUE_NAME, reference=case.case_number)
        eflyt_search.open_case(browser, case.case_number)
        if handle_case(browser, case):
            orchestrator_connection.log_info(f"Case {case.case_number} approved.")
            itk_dev_event_log.emit(orchestrator_connection.process_name, "Case approved.")
        orchestrator_connection.set_queue_element_status(queue_element.id, QueueStatus.DONE)


def filter_cases(cases: list[Case]) -> list[Case]:
    """Filter cases based on the assigned case worker.
    If the first two letters are EF and the rest are numbers, the case has received a reply on a lodging request.

    Args:
        cases: List of cases to filter.

    Returns:
        Filtered cases that needs to be checked further.
    """
    approved_case_types = [
        "Logivært",
        "Boligselskab",
        "Manuel opgave",
        "CPR notat",
        "Særlig adresse"
    ]

    # Only work on cases in the format EF1234, that only have one case type within the approved types
    filtered_cases = []
    for case in cases:
        if case.case_worker[:2].upper() == "EF" and case.case_worker[2:].isdigit() and all(t in approved_case_types for t in case.case_types) and "Logivært" in case.case_types:
            filtered_cases.append(case)
    return filtered_cases


def handle_case(browser: webdriver.Chrome, case: Case) -> bool:
    """Check dates on each case, approve all cases where dates match.

    Args:
        browser: A selenium webdriver that has navigated to the case.

    Returns:
        Whether the case was approved or not
    """
    if "Boligselskab" in case.case_types and len(eflyt_case.get_beboere(browser)) != 0:
        return False

    eflyt_case.change_tab(browser, 0)
    registered_date = browser.find_element(By.ID, "ctl00_ContentPlaceHolder2_GridViewMovingPersons_ctl02_lnkDateCPR").text
    vis_svar_element = browser.find_element(By.LINK_TEXT, "Vis svar")
    if vis_svar_element:
        vis_svar_element.click()
    else:
        return False
    from_date_element = WebDriverWait(browser, 10).until(
        EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder2_ptFanePerson_moPersonTab_txtFradato"))
    )
    response_date = from_date_element.get_attribute("value")

    selection_table = browser.find_element(By.ID, "ctl00_ContentPlaceHolder2_ptFanePerson_moPersonTab_rdoEDSLogivartResponseType")
    request_match = False
    for option in selection_table.find_elements(By.TAG_NAME, "td"):
        selected = option.find_element(By.TAG_NAME, "input").get_attribute("checked") == "true"
        content = option.find_element(By.TAG_NAME, "label").text
        if selected and content == "Skal bo og opholde sig på min adresse":
            request_match = True
            break

    browser.find_element(By.ID, "ctl00_ContentPlaceHolder2_ptFanePerson_moPersonTab_btnLogivartResponseLuk").click()

    if registered_date == response_date and request_match:  # Approve the case
        eflyt_case.approve_case(browser)
        if not eflyt_case.check_all_approved(browser):
            raise RuntimeError("An error occurred during case approval.")
        note_text = "Datoer stemmer overens, flytning godkendt."
        if "Boligselskab" in case.case_types:
            note_text += " Ingen beboere fundet på adressen."
        eflyt_case.add_note(browser, note_text)
        return True
    return False


if __name__ == '__main__':
    conn_string = os.getenv("OpenOrchestratorConnString")
    crypto_key = os.getenv("OpenOrchestratorKey")
    oc = OrchestratorConnection("Eflyt Test", conn_string, crypto_key, "", '')
    process(oc)
