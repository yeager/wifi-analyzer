Name:           wifi-analyzer
Version:        0.1.31
Release:        1%{?dist}
Summary:        GTK application for inspecting nearby Wi-Fi networks
License:        GPL-3.0-or-later
URL:            https://github.com/yeager/wifi-analyzer
Source0:        %{name}-%{version}.tar.gz

BuildArch:       noarch
BuildRequires:   appstream
BuildRequires:   desktop-file-utils
BuildRequires:   gettext
BuildRequires:   gtk4
BuildRequires:   libadwaita
BuildRequires:   python3-devel
BuildRequires:   python3-pytest
BuildRequires:   python3dist(setuptools)
BuildRequires:   python3dist(setuptools-scm)
BuildRequires:   xorg-x11-server-Xvfb
Requires:        NetworkManager
Requires:        iw
Requires:        libadwaita
Requires:        python3-cairo
Requires:        python3-gobject

%description
WiFi Analyzer displays nearby access points, their signal strength, channel,
security mode, overlap and regulatory hints through NetworkManager.

%prep
%autosetup

%build
python3 scripts/compile_translations.py
%pyproject_wheel

%install
%pyproject_install
install -Dpm0644 data/io.github.yeager.wifi-analyzer.desktop \
  %{buildroot}%{_datadir}/applications/io.github.yeager.wifi-analyzer.desktop
install -Dpm0644 data/io.github.yeager.wifi-analyzer.metainfo.xml \
  %{buildroot}%{_metainfodir}/io.github.yeager.wifi-analyzer.metainfo.xml
install -Dpm0644 docs/man/wifi-analyzer.1 \
  %{buildroot}%{_mandir}/man1/wifi-analyzer.1
install -Dpm0644 docs/man/sv/wifi-analyzer.1 \
  %{buildroot}%{_mandir}/sv/man1/wifi-analyzer.1
install -Dpm0644 data/icons/hicolor/256x256/apps/io.github.yeager.wifi-analyzer.png \
  %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/io.github.yeager.wifi-analyzer.png
install -Dpm0644 data/icons/hicolor/512x512/apps/io.github.yeager.wifi-analyzer.png \
  %{buildroot}%{_datadir}/icons/hicolor/512x512/apps/io.github.yeager.wifi-analyzer.png
for mo in locale/*/LC_MESSAGES/wifi-analyzer.mo; do
  lang=$(basename $(dirname $(dirname "$mo")))
  install -Dpm0644 "$mo" %{buildroot}%{_datadir}/locale/$lang/LC_MESSAGES/wifi-analyzer.mo
done

%check
GSK_RENDERER=cairo xvfb-run -a env PYTHONPATH=src pytest -q

%files
%license LICENSE
%doc README.md
%{_bindir}/wifi-analyzer
%{python3_sitelib}/wifi_analyzer/
%{python3_sitelib}/wifi_analyzer-*.dist-info/
%{_datadir}/applications/io.github.yeager.wifi-analyzer.desktop
%{_metainfodir}/io.github.yeager.wifi-analyzer.metainfo.xml
%{_mandir}/man1/wifi-analyzer.1*
%{_mandir}/sv/man1/wifi-analyzer.1*
%{_datadir}/icons/hicolor/*/apps/io.github.yeager.wifi-analyzer.png
%{_datadir}/locale/*/LC_MESSAGES/wifi-analyzer.mo

%changelog
* Fri Oct 30 2026 Daniel Nylander <po@danielnylander.se> - 0.1.31-1
- Expose saved signal-history plots and measurements to screen readers.

* Fri Oct 30 2026 Daniel Nylander <po@danielnylander.se> - 0.1.30-1
- Resolve release commits from the verified GitHub event when a local tag ref is unavailable.

* Fri Oct 30 2026 Daniel Nylander <po@danielnylander.se> - 0.1.29-1
- Escape untrusted values in diagnostic reports.
- Restrict Flatpak permissions and strengthen release and package checks.

* Fri Oct 30 2026 Daniel Nylander <po@danielnylander.se> - 0.1.28-1
- Read connection link rates from the active NetworkManager Wi-Fi adapter.

* Fri Oct 30 2026 Daniel Nylander <po@danielnylander.se> - 0.1.27-1
- Prefer the connected Wi-Fi adapter when multiple devices are available.

* Fri Oct 30 2026 Daniel Nylander <po@danielnylander.se> - 0.1.26-1
- Respect locally reported regulatory ranges in channel recommendations.

* Thu Oct 29 2026 Daniel Nylander <po@danielnylander.se> - 0.1.25-1
- Clarify limits of scan-based channel overlap recommendations.
- Add Swedish guidance and update the demonstration screenshot.

* Thu Oct 29 2026 Daniel Nylander <po@danielnylander.se> - 0.1.24-1
- Escape formula-like untrusted text in CSV exports.
- Allow the Flatpak manifest to track the latest published release during development.

* Thu Oct 29 2026 Daniel Nylander <po@danielnylander.se> - 0.1.23-1
- Add Occitan and German translations and clarify partial catalogue behavior.

* Thu Oct 29 2026 Daniel Nylander <po@danielnylander.se> - 0.1.22-1
- Use the exact GitHub repository slug in the application ID.

* Thu Oct 29 2026 Daniel Nylander <po@danielnylander.se> - 0.1.21-1
- Match the desktop application ID to the GitHub repository slug.

* Thu Oct 29 2026 Daniel Nylander <po@danielnylander.se> - 0.1.20-1
- Add keyboard navigation and screen-reader support to the channel graph.
- Require a complete, validated Swedish translation catalogue.

* Sun Oct 25 2026 Daniel Nylander <po@danielnylander.se> - 0.1.19-1
- Prepare PyPI release, bundle translations, and synchronize version metadata.

* Tue Sep 22 2026 Daniel Nylander <po@danielnylander.se> - 0.1.18-1
- Fix direct launch with Python from the source directory.

* Mon Sep 21 2026 Daniel Nylander <po@danielnylander.se> - 0.1.17-1
- Add zoom and guidance to the interactive channel view.
