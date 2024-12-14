The `epson workforce` platform allows you to monitor the ink levels of a Epson WorkForce printer from Home
Assistant.

To add Epson WorkForce to your installation, add the following to your `configuration.yaml` file:

```yaml
# Example configuration.yaml entry
sensor:
   - platform: epson_workforce
     host: IP_ADDRESS
     monitored_conditions:
     - black
     - photoblack
     - yellow
     - magenta
     - cyan
     - lightmagenta
     - lightcyan
     - clean
```

{% configuration %}
host:
  description: The host name or address of the Epson workforce printer
  required: true
  type: string
monitored_conditions:
  description: The cartridge colours to monitor.
  required: true
  type: list
  keys:
    black:
      description: The black ink cartridge
    photoblack:
      description: The photo black ink cartridge (not supported by all printers).
    yellow:
      description: The yellow ink cartridge.
    magenta:
      description: The magenta (=red) ink cartridge.
    cyan:
      description: The cyan (=blue) ink cartridge.
    lightmagenta:
      description: The light magenta (=red) ink cartridge.
    lightcyan:
      description: The light cyan (=blue) ink cartridge.
    clean:
      description: The cleaning cartridge.
{% endconfiguration %}

Supported devices:

- Epson WorkForce (and some EcoTank) printers who publish a HTTP page containing the ink cartridge levels

Tested devices:

- Epson WF2630
- Epson WF2660
- Epson WF3540
- Epson WF3620
- Epson WF3640
- Epson WF4820
- Epson EcoTank ET-77x0
- Epson ET-2650
- EPSON ET-2750
- Epson ET-4750
- Epson EcoTank ET-5150 (51x0)
- Epson Expression Home XP-2100
- Epson Expression Home XP-2105

To make this module work you need to connect your printer to your LAN.
The best is to navigate to the status page of the printer to check if it shows the page with the ink levels on the URL `http://<IP_ADDRESS>/PRESENTATION/HTML/TOP/PRTINFO.HTML`
