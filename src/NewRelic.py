import json
import os

from python_graphql_client import GraphqlClient

import src.utils.constants as constants
from src.Dashboard import Dashboard
from src.PromQL2NrqlService import PromQL2NrqlService


class NewRelic:

    def __init__(self, config):

        self.config = config
        self.userKey = config['api']['userKey']
        self.accountId = config['api']['accountId']

        self.createOutputDir()

    def createOutputDir(self):
        # Create output directory if it doesn't exist
        if not os.path.exists(constants.OUTPUT_DIR):
            os.makedirs(constants.OUTPUT_DIR)

        if not os.path.exists(constants.NEWRELIC_OUTPUT_DIR):
            os.makedirs(constants.NEWRELIC_OUTPUT_DIR)

    def convert(self, grafana_dashboard):

        try:
            # Read file
            with open(grafana_dashboard, 'r') as f:
                data = json.load(f)

            # Some dashboards we get may not be wrapped in parent "dashboard" json
            # We will convert those to the schema we expect
            if 'dashboard' not in data:
                data = {"dashboard": data}

            # Conversion service
            variables = Dashboard.getVariables(data)
            promQL2NrqlService = PromQL2NrqlService(self.config, variables)

            # Create and parse dashboard
            print(f"Starting Conversion: {grafana_dashboard}")
            new_relic_dashboard = Dashboard(promQL2NrqlService, data)

            self.dumpDataToFile(grafana_dashboard, new_relic_dashboard, "original")

            # remove widgets with errors
            removed_widgets = self.removeWidgetsWithError(new_relic_dashboard)

            self.dumpDataToFile(grafana_dashboard, new_relic_dashboard, "updated")

            self.dumpDataToFile(grafana_dashboard, removed_widgets, "removed_widgets")

        except Exception as e:
            print(f"Error converting dashboard: {e}")

    def removeWidgetsWithError(self, new_relic_dashboard):
        removed_widgets = []

        for page in new_relic_dashboard.pages:
            page_widgets_to_remove = []
            try:
                for widget in page.widgets:
                    try:
                        if not hasattr(widget, 'visualisation') or widget.visualisation is None \
                                or not widget.rawConfiguration.get('nrqlQueries') or len(
                            widget.rawConfiguration['nrqlQueries']) == 0:
                            page_widgets_to_remove.append(widget)
                            continue
                        else:
                            for query in widget.rawConfiguration['nrqlQueries']:
                                if 'KeyError' in query:
                                    page_widgets_to_remove.append(widget)
                                    break
                    except AttributeError as e:
                        print(f"Error removing widget {widget.id} {widget.toJSON()} with errors: {e}")
                        raise e
            except Exception as e:
                print(f"Error occurred: {e}")
                raise e

            for widget in page_widgets_to_remove:
                removed_widgets.append(widget)
                page.widgets.remove(widget)

        return removed_widgets

    def dumpDataToFile(self, grafana_dashboard, data, file_suffix):

        # if data is an array of widgets, convert to array of json
        if isinstance(data, list):
            output = json.dumps(list(map(lambda widget: widget.toJSON(), data)), indent=4, sort_keys=True)
        else:
            output = json.dumps(data.toJSON(), indent=4, sort_keys=True)

        # Write out file
        file_path = f"{constants.NEWRELIC_OUTPUT_DIR}/newrelic-{os.path.basename(grafana_dashboard)}_{file_suffix}"

        with open(file_path, 'w') as f:
            f.write(output)

        return file_path

    def importDashboard(self, file):

        print(f"Importing Dashboard: {file}")
        # Read dashboard json file
        with open(file, 'r') as f:
            dashboard = json.load(f)

        # Instantiate the client with an endpoint.
        client = GraphqlClient(endpoint=constants.GRAPHQL_URL, headers={"API-Key": self.userKey})

        # Create the query string and variables required for the request.
        query = constants.CREATE_DASHBOARD_MUTATION
        variables = {
            "accountId": self.accountId,
            "dashboard": dashboard,
        }

        # Synchronous request
        data = client.execute(query=query, variables=variables)
        print(json.dumps(data, indent=3))
