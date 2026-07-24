"""HLTs for bbtautau analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from boostedhh import utils

years_2022 = ["2022", "2022EE"]
years_2023 = ["2023", "2023BPix"]
years_2024 = ["2024"]
years = years_2022 + years_2023 + years_2024


@dataclass
class HLT(utils.HLT):
    """Same as boostedhh.utils.HLT but with channel."""

    # which channel? defaults to all.
    channel: list[str] = field(default_factory=lambda: ["hh", "hm", "he"])


class HLTs:
    HLTs: ClassVar[dict[str, list[HLT]]] = {
        #     mc_years=[],
        #     data_years=["2023"],
        #     dataset="JetMET",
        # ),
        # 2022 + 2023
        # HLT(
        #     name="HLT_DoubleMediumDeepTauPFTauHPS30_L2NN_eta2p1_PFJet75",
        #     years=years,
        #     dataset="Tau",
        #     channel=["hh"],
        # ),
        "muon": [
            HLT(
                name="HLT_IsoMu24",
                years=years,
                dataset="Muon",
            ),
            # TODO: check sensitivity without below triggers
            HLT(
                name="HLT_Mu17_TrkIsoVVL_Mu8_TrkIsoVVL_DZ_Mass3p8",
                years=years,
                dataset="Muon",
            ),
        ],
        "egamma": [
            # "egamma" dict key is a separate namespace: a lepton-flavour bucket
            # (muon / egamma / emu), not a PD name.

            # The single-electron path must stay first in this list: objects.trig_match_sel
            # resolves the electron trigger as hlts_by_type(year, "EGamma")[0]. The year
            # ranges below are exclusive, so exactly one single-e path survives per year.
            # TODO: 2023 still uses Ele32; decide whether it should move to Ele30.
            HLT(
                name="HLT_Ele32_WPTight_Gsf",
                years=years_2022 + years_2023,
                dataset="EGamma",   
                # "EGamma" is the correct dataset for Ele30/Ele32. 
                # In Run 3, CMS merged the Run 2 SingleElectron + DoubleEG + SinglePhoton 
                # primary datasets into one PD named "EGamma".
            ),
            HLT(
                name="HLT_Ele30_WPTight_Gsf",
                years=years_2024,
                dataset="EGamma",
            ),
            HLT(
                name="HLT_Ele23_Ele12_CaloIdL_TrackIdL_IsoVL",
                years=years,
                dataset="EGamma",
            ),
        ],
        "emu": [
            HLT(
                name="HLT_Mu23_TrkIsoVVL_Ele12_CaloIdL_TrackIdL_IsoVL",
                years=years,
                dataset="EGamma",
            ),
            HLT(
                name="HLT_Mu8_TrkIsoVVL_Ele23_CaloIdL_TrackIdL_IsoVL_DZ",
                years=years,
                dataset="EGamma",
            ),
            HLT(
                name="HLT_Mu12_TrkIsoVVL_Ele23_CaloIdL_TrackIdL_IsoVL_DZ",
                years=years,
                dataset="EGamma",
            ),
        ],
    }

    @classmethod
    def hlt_dict(
        cls,
        year: str,
        as_str: bool = True,
        hlt_prefix: bool = True,
        data_only: bool = False,
        mc_only: bool = False,
    ) -> dict[str, list[HLT | str]]:
        """
        Convert into a dictionary of HLTs per year, optionally filtered by data or MC.

        Args:
            year (str): year to filter by.
            as_str (bool): if True, return HLT names only. If False, return HLT objects. Defaults to True.
            data_only (bool): filter by HLTs in data for that year. Defaults to False.
            mc_only (bool): filter by HLTs in MC for that year. Defaults to False.

        Returns:
            dict[str, list[HLT | str]]: format is ``{hlt_type: [hlt, ...]}``
        """
        if data_only and mc_only:
            raise ValueError("Cannot filter by both data and MC")

        return {
            hlt_type: [
                (hlt.get_name(hlt_prefix) if as_str else hlt)
                for hlt in hlt_list
                if hlt.check_year(year, data_only, mc_only)
            ]
            for hlt_type, hlt_list in cls.HLTs.items()
        }

    @classmethod
    def hlt_list(
        cls, as_str: bool = True, hlt_prefix: bool = True, **hlt_kwargs
    ) -> dict[str, list[HLT | str]]:
        """
        Combine into a dict of lists of HLTs per year.

        Args:
            as_str (bool): if True, return HLT names only. If False, return HLT objects. Defaults to True.
            hlt_prefix (bool): if True, return HLT names with "HLT_" prefix. If False, return HLT names without "HLT_" prefix. Defaults to True.
            **hlt_kwargs: additional kwargs to pass to the hlt_dict function.

        Returns:
            dict[str, list[HLT | str]]: format is ``{year: [hlt, ...]}``
        """
        return {
            year: [
                (hlt.get_name(hlt_prefix) if as_str else hlt)
                for sublist in cls.hlt_dict(year, as_str=False, **hlt_kwargs).values()
                for hlt in sublist
            ]
            for year in years
        }

    @classmethod
    def hlts_by_type(
        cls,
        year: str,
        hlt_type: str | list[str],
        **hlt_kwargs,
    ) -> list[HLT | str]:
        """
        HLTs per year and type(s), with optional filters.

        Args:
            year (str): year to filter by.
            hlt_type (str | list[str]): filter by HLT type(s) out of ["PNet", "PFJet", "QuadJet", "DiTau", "SingleTau", "Muon", "EGamma", "MET", "Parking"].
            **hlt_kwargs: additional kwargs to pass to the hlt_dict function.

        Returns:
            list[HLT | str]: list of HLTs. Returns strings if as_str=True is passed in hlt_kwargs, otherwise returns HLT objects.
        """
        hlts = cls.hlt_dict(year, **hlt_kwargs)

        if isinstance(hlt_type, str):
            return hlts[hlt_type.lower()]
        else:
            return [hlt for ht in hlt_type for hlt in hlts[ht.lower()]]

    @classmethod
    def hlts_by_dataset(
        cls,
        year: str,
        dataset: str,
        as_str: bool = True,
        hlt_prefix: bool = True,
        **hlt_kwargs,
    ) -> list[HLT | str]:
        """
        HLTs per year and dataset, with optional filters.

        Args:
            year (str): year to filter by.
            dataset (str): filter by dataset out of ["JetMET", "Tau", "Muon", "EGamma", "ParkingHH"].
            as_str (bool): if True, return HLT names only. If False, return HLT objects. Defaults to True.
            hlt_prefix (bool): if True, return HLT names with "HLT_" prefix. If False, return HLT names without "HLT_" prefix. Defaults to True.
            **hlt_kwargs: additional kwargs to pass to the hlt_list function.

        Returns:
            list[HLT | str]: list of HLTs
        """
        hlts = cls.hlt_list(False, **hlt_kwargs)[year]
        ret_hlts = [
            (hlt.get_name(hlt_prefix) if as_str else hlt)
            for hlt in hlts
            if hlt.dataset.lower() == dataset.lower()
        ]

        if len(ret_hlts) == 0:
            raise ValueError(f"Dataset {dataset} not found in HLTs")

        return ret_hlts

    @classmethod
    def hlts_list_by_dtype(
        cls,
        year: str,
        as_str: bool = True,
        hlt_prefix: bool = True,
        **hlt_kwargs,
    ) -> list[HLT | str]:
        """
        HLTs per year, with optional filters.

        Args:
            year (str): year to filter by.
            as_str (bool): if True, return HLT names only. If False, return HLT objects. Defaults to True.
            hlt_prefix (bool): if True, return HLT names with "HLT_" prefix. If False, return HLT names without "HLT_" prefix. Defaults to True.
            **hlt_kwargs: additional kwargs to pass to the hlt_list function.

        Returns:
            dict[str, list[HLT | str]]: format is ``{data: [hlt, ...], signal: [...]}``
        """
        return {
            "signal": [
                (hlt.get_name(hlt_prefix) if as_str else hlt)
                for sublist in cls.hlt_dict(year, as_str=False, mc_only=True, **hlt_kwargs).values()
                for hlt in sublist
            ],
            "bg": [
                (hlt.get_name(hlt_prefix) if as_str else hlt)
                for sublist in cls.hlt_dict(year, as_str=False, mc_only=True, **hlt_kwargs).values()
                for hlt in sublist
            ],
            "data": [
                (hlt.get_name(hlt_prefix) if as_str else hlt)
                for sublist in cls.hlt_dict(
                    year, as_str=False, data_only=True, **hlt_kwargs
                ).values()
                for hlt in sublist
            ],
        }

    @classmethod
    def get_hlt(cls, name: str) -> HLT:
        for cat in cls.HLTs.values():
            for hlt in cat:
                if hlt.get_name() == name:
                    return hlt
        raise ValueError(f"HLT {name} not found in HLTs")
