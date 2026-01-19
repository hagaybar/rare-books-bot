"""Tests for enhanced agent extraction (Stage 2) and authority URI extraction."""

import pytest
from pymarc import Record, Field, Subfield

from scripts.marc.parse import extract_agents, extract_subjects, AgentData


class TestPersonalNameExtraction:
    """Test extraction of personal names (100/700)."""

    def test_personal_name_main_entry(self):
        """Test extraction from 100 field (main personal name)."""
        record = Record()
        record.add_field(
            Field(
                tag='100',
                indicators=['1', ' '],
                subfields=[
                    Subfield(code='a', value='Smith, John,'),
                    Subfield(code='d', value='1950-'),
                ]
            )
        )

        agents = extract_agents(record)

        assert len(agents) == 1
        agent = agents[0]
        assert agent.name.value == 'Smith, John,'
        assert agent.entry_role == 'main'
        assert agent.agent_type == 'personal'
        assert agent.agent_index == 0
        assert agent.dates.value == '1950-'
        # Main entries get inferred role if no explicit relator
        assert agent.role_source == 'inferred_from_tag'
        assert agent.function.value == 'author'

    def test_personal_name_added_entry_with_relator_code(self):
        """Test extraction from 700 field with $4 relator code."""
        record = Record()
        record.add_field(
            Field(
                tag='700',
                indicators=['1', ' '],
                subfields=[
                    Subfield(code='a', value='Jones, Mary,'),
                    Subfield(code='d', value='1960-2020'),
                    Subfield(code='4', value='prt'),  # printer
                ]
            )
        )

        agents = extract_agents(record)

        assert len(agents) == 1
        agent = agents[0]
        assert agent.name.value == 'Jones, Mary,'
        assert agent.entry_role == 'added'
        assert agent.agent_type == 'personal'
        assert agent.agent_index == 0
        assert agent.dates.value == '1960-2020'
        assert agent.role_source == 'relator_code'
        assert agent.function.value == 'prt'
        assert '700[0]$4' in agent.function.source

    def test_personal_name_added_entry_with_relator_term(self):
        """Test extraction from 700 field with $e relator term."""
        record = Record()
        record.add_field(
            Field(
                tag='700',
                indicators=['1', ' '],
                subfields=[
                    Subfield(code='a', value='Brown, Alice'),
                    Subfield(code='e', value='translator'),
                ]
            )
        )

        agents = extract_agents(record)

        assert len(agents) == 1
        agent = agents[0]
        assert agent.name.value == 'Brown, Alice'
        assert agent.entry_role == 'added'
        assert agent.agent_type == 'personal'
        assert agent.role_source == 'relator_term'
        assert agent.function.value == 'translator'
        assert '700[0]$e' in agent.function.source

    def test_personal_name_priority_relator_code_over_term(self):
        """Test that $4 relator code takes priority over $e term."""
        record = Record()
        record.add_field(
            Field(
                tag='700',
                indicators=['1', ' '],
                subfields=[
                    Subfield(code='a', value='Garcia, Luis'),
                    Subfield(code='e', value='editor'),
                    Subfield(code='4', value='trl'),  # Should win
                ]
            )
        )

        agents = extract_agents(record)

        assert len(agents) == 1
        agent = agents[0]
        assert agent.role_source == 'relator_code'
        assert agent.function.value == 'trl'
        assert '700[0]$4' in agent.function.source

    def test_personal_name_without_role(self):
        """Test extraction when no role information is available."""
        record = Record()
        record.add_field(
            Field(
                tag='700',
                indicators=['1', ' '],
                subfields=[
                    Subfield(code='a', value='Kim, Ji-won'),
                ]
            )
        )

        agents = extract_agents(record)

        assert len(agents) == 1
        agent = agents[0]
        assert agent.role_source == 'unknown'
        assert agent.function is None


class TestCorporateBodyExtraction:
    """Test extraction of corporate bodies (110/710)."""

    def test_corporate_main_entry(self):
        """Test extraction from 110 field (main corporate name)."""
        record = Record()
        record.add_field(
            Field(
                tag='110',
                indicators=['2', ' '],
                subfields=[
                    Subfield(code='a', value='Oxford University Press.'),
                ]
            )
        )

        agents = extract_agents(record)

        assert len(agents) == 1
        agent = agents[0]
        assert agent.name.value == 'Oxford University Press.'
        assert agent.entry_role == 'main'
        assert agent.agent_type == 'corporate'
        assert agent.agent_index == 0
        assert agent.dates is None  # Corporate bodies don't have dates
        assert agent.role_source == 'inferred_from_tag'
        assert agent.function.value == 'creator'

    def test_corporate_with_subordinate_unit(self):
        """Test extraction of corporate body with subordinate unit ($b)."""
        record = Record()
        record.add_field(
            Field(
                tag='710',
                indicators=['2', ' '],
                subfields=[
                    Subfield(code='a', value='Harvard University.'),
                    Subfield(code='b', value='Library.'),
                    Subfield(code='4', value='pbl'),  # publisher
                ]
            )
        )

        agents = extract_agents(record)

        assert len(agents) == 1
        agent = agents[0]
        assert agent.name.value == 'Harvard University. Library.'
        assert agent.entry_role == 'added'
        assert agent.agent_type == 'corporate'
        assert agent.role_source == 'relator_code'
        assert agent.function.value == 'pbl'
        # Check that sources include both $a and $b
        assert len(agent.name.source) == 2
        assert '710[0]$a' in agent.name.source
        assert '710[0]$b' in agent.name.source

    def test_corporate_with_role(self):
        """Test corporate body with explicit role."""
        record = Record()
        record.add_field(
            Field(
                tag='710',
                indicators=['2', ' '],
                subfields=[
                    Subfield(code='a', value='Elsevier,'),
                    Subfield(code='e', value='publisher'),
                ]
            )
        )

        agents = extract_agents(record)

        assert len(agents) == 1
        agent = agents[0]
        assert agent.name.value == 'Elsevier,'
        assert agent.agent_type == 'corporate'
        assert agent.role_source == 'relator_term'
        assert agent.function.value == 'publisher'


class TestMeetingExtraction:
    """Test extraction of meeting names (111/711)."""

    def test_meeting_main_entry(self):
        """Test extraction from 111 field (main meeting name)."""
        record = Record()
        record.add_field(
            Field(
                tag='111',
                indicators=['2', ' '],
                subfields=[
                    Subfield(code='a', value='Vatican Council'),
                    Subfield(code='n', value='(2nd :'),
                    Subfield(code='d', value='1962-1965 :'),
                    Subfield(code='c', value='Vatican City)'),
                ]
            )
        )

        agents = extract_agents(record)

        assert len(agents) == 1
        agent = agents[0]
        assert 'Vatican Council' in agent.name.value
        assert '(2nd :' in agent.name.value
        assert 'Vatican City)' in agent.name.value
        assert agent.entry_role == 'main'
        assert agent.agent_type == 'meeting'
        assert agent.agent_index == 0
        assert agent.dates.value == '1962-1965 :'
        assert agent.role_source == 'inferred_from_tag'
        assert agent.function.value == 'creator'

    def test_meeting_added_entry_with_role(self):
        """Test extraction from 711 field with role."""
        record = Record()
        record.add_field(
            Field(
                tag='711',
                indicators=['2', ' '],
                subfields=[
                    Subfield(code='a', value='International Conference on Machine Learning'),
                    Subfield(code='n', value='(37th :'),
                    Subfield(code='d', value='2020 :'),
                    Subfield(code='c', value='Virtual)'),
                    Subfield(code='4', value='aut'),
                ]
            )
        )

        agents = extract_agents(record)

        assert len(agents) == 1
        agent = agents[0]
        assert 'International Conference on Machine Learning' in agent.name.value
        assert agent.entry_role == 'added'
        assert agent.agent_type == 'meeting'
        assert agent.dates.value == '2020 :'
        assert agent.role_source == 'relator_code'
        assert agent.function.value == 'aut'
        # Check that sources include $a, $n, $c
        assert len(agent.name.source) == 3


class TestMultipleAgents:
    """Test extraction of multiple agents from a single record."""

    def test_multiple_personal_names(self):
        """Test extraction of multiple personal names."""
        record = Record()
        record.add_field(
            Field(
                tag='100',
                indicators=['1', ' '],
                subfields=[
                    Subfield(code='a', value='Primary, Author'),
                ]
            )
        )
        record.add_field(
            Field(
                tag='700',
                indicators=['1', ' '],
                subfields=[
                    Subfield(code='a', value='Second, Author'),
                    Subfield(code='4', value='aut'),
                ]
            )
        )
        record.add_field(
            Field(
                tag='700',
                indicators=['1', ' '],
                subfields=[
                    Subfield(code='a', value='Third, Person'),
                    Subfield(code='e', value='editor'),
                ]
            )
        )

        agents = extract_agents(record)

        assert len(agents) == 3
        assert agents[0].agent_index == 0
        assert agents[1].agent_index == 1
        assert agents[2].agent_index == 2
        assert agents[0].name.value == 'Primary, Author'
        assert agents[1].name.value == 'Second, Author'
        assert agents[2].name.value == 'Third, Person'

    def test_mixed_agent_types(self):
        """Test extraction of mixed agent types (personal, corporate, meeting)."""
        record = Record()
        record.add_field(
            Field(
                tag='100',
                indicators=['1', ' '],
                subfields=[
                    Subfield(code='a', value='Smith, John'),
                ]
            )
        )
        record.add_field(
            Field(
                tag='710',
                indicators=['2', ' '],
                subfields=[
                    Subfield(code='a', value='MIT Press'),
                    Subfield(code='4', value='pbl'),
                ]
            )
        )
        record.add_field(
            Field(
                tag='711',
                indicators=['2', ' '],
                subfields=[
                    Subfield(code='a', value='Symposium on X'),
                ]
            )
        )

        agents = extract_agents(record)

        assert len(agents) == 3
        assert agents[0].agent_type == 'personal'
        assert agents[1].agent_type == 'corporate'
        assert agents[2].agent_type == 'meeting'
        assert agents[0].agent_index == 0
        assert agents[1].agent_index == 1
        assert agents[2].agent_index == 2

    def test_agent_index_stable_ordering(self):
        """Test that agent_index provides stable ordering."""
        record = Record()
        # Add multiple agents in specific order
        record.add_field(
            Field(tag='110', indicators=['2', ' '],
                  subfields=[Subfield(code='a', value='Corp A')])
        )
        record.add_field(
            Field(tag='700', indicators=['1', ' '],
                  subfields=[Subfield(code='a', value='Person B')])
        )
        record.add_field(
            Field(tag='700', indicators=['1', ' '],
                  subfields=[Subfield(code='a', value='Person C')])
        )
        record.add_field(
            Field(tag='710', indicators=['2', ' '],
                  subfields=[Subfield(code='a', value='Corp D')])
        )

        agents = extract_agents(record)

        assert len(agents) == 4
        # Verify indexes are sequential and stable
        for i, agent in enumerate(agents):
            assert agent.agent_index == i


class TestAuthorityURIExtraction:
    """Test extraction of authority URIs from $0 subfield."""

    def test_personal_name_with_authority_uri(self):
        """Test extraction of authority URI from personal name (100)."""
        record = Record()
        record.add_field(
            Field(
                tag='100',
                indicators=['1', ' '],
                subfields=[
                    Subfield(code='a', value='Manutius, Aldus,'),
                    Subfield(code='d', value='1449-1515'),
                    Subfield(code='0', value='https://open-eu.hosted.exlibrisgroup.com/alma/972NNL_INST/authorities/987007261327805171.jsonld'),
                ]
            )
        )

        agents = extract_agents(record)

        assert len(agents) == 1
        agent = agents[0]
        assert agent.name.value == 'Manutius, Aldus,'
        assert agent.authority_uri is not None
        assert agent.authority_uri.value == 'https://open-eu.hosted.exlibrisgroup.com/alma/972NNL_INST/authorities/987007261327805171.jsonld'
        assert '100[0]$0' in agent.authority_uri.source

    def test_corporate_body_with_authority_uri(self):
        """Test extraction of authority URI from corporate body (710)."""
        record = Record()
        record.add_field(
            Field(
                tag='710',
                indicators=['2', ' '],
                subfields=[
                    Subfield(code='a', value='Aldine Press.'),
                    Subfield(code='0', value='http://viaf.org/viaf/123456789'),
                    Subfield(code='4', value='pbl'),
                ]
            )
        )

        agents = extract_agents(record)

        assert len(agents) == 1
        agent = agents[0]
        assert agent.name.value == 'Aldine Press.'
        assert agent.agent_type == 'corporate'
        assert agent.authority_uri is not None
        assert agent.authority_uri.value == 'http://viaf.org/viaf/123456789'
        assert '710[0]$0' in agent.authority_uri.source

    def test_meeting_with_authority_uri(self):
        """Test extraction of authority URI from meeting (711)."""
        record = Record()
        record.add_field(
            Field(
                tag='711',
                indicators=['2', ' '],
                subfields=[
                    Subfield(code='a', value='Council of Trent'),
                    Subfield(code='d', value='1545-1563'),
                    Subfield(code='c', value='Trento, Italy'),
                    Subfield(code='0', value='http://id.loc.gov/authorities/names/n12345678'),
                ]
            )
        )

        agents = extract_agents(record)

        assert len(agents) == 1
        agent = agents[0]
        assert 'Council of Trent' in agent.name.value
        assert agent.agent_type == 'meeting'
        assert agent.authority_uri is not None
        assert agent.authority_uri.value == 'http://id.loc.gov/authorities/names/n12345678'
        assert '711[0]$0' in agent.authority_uri.source

    def test_agent_without_authority_uri(self):
        """Test that agents without $0 have authority_uri=None."""
        record = Record()
        record.add_field(
            Field(
                tag='700',
                indicators=['1', ' '],
                subfields=[
                    Subfield(code='a', value='Unknown Author'),
                ]
            )
        )

        agents = extract_agents(record)

        assert len(agents) == 1
        assert agents[0].authority_uri is None


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_record(self):
        """Test extraction from record with no agents."""
        record = Record()
        agents = extract_agents(record)
        assert len(agents) == 0

    def test_field_without_subfield_a(self):
        """Test that fields without $a are skipped."""
        record = Record()
        record.add_field(
            Field(
                tag='700',
                indicators=['1', ' '],
                subfields=[
                    Subfield(code='d', value='1950-'),  # No $a
                ]
            )
        )

        agents = extract_agents(record)
        assert len(agents) == 0

    def test_multiple_occurrences_same_tag(self):
        """Test correct occurrence tracking for multiple fields with same tag."""
        record = Record()
        record.add_field(
            Field(tag='700', indicators=['1', ' '],
                  subfields=[Subfield(code='a', value='First Author')])
        )
        record.add_field(
            Field(tag='700', indicators=['1', ' '],
                  subfields=[Subfield(code='a', value='Second Author')])
        )

        agents = extract_agents(record)

        assert len(agents) == 2
        # Check that source references have correct occurrence numbers
        assert '700[0]$a' in agents[0].name.source
        assert '700[1]$a' in agents[1].name.source

    def test_all_main_entry_types(self):
        """Test that only relevant main entry tags are processed."""
        record = Record()
        record.add_field(
            Field(tag='100', indicators=['1', ' '],
                  subfields=[Subfield(code='a', value='Person')])
        )
        record.add_field(
            Field(tag='110', indicators=['2', ' '],
                  subfields=[Subfield(code='a', value='Corporate')])
        )
        record.add_field(
            Field(tag='111', indicators=['2', ' '],
                  subfields=[Subfield(code='a', value='Meeting')])
        )
        record.add_field(
            Field(tag='130', indicators=['0', ' '],
                  subfields=[Subfield(code='a', value='Uniform Title')])
        )

        agents = extract_agents(record)

        # Should extract 100, 110, 111 but not 130 (uniform title)
        assert len(agents) == 3
        assert agents[0].agent_type == 'personal'
        assert agents[1].agent_type == 'corporate'
        assert agents[2].agent_type == 'meeting'


class TestSubjectAuthorityURIExtraction:
    """Test extraction of authority URIs from subject $0 subfields."""

    def test_subject_with_authority_uri(self):
        """Test extraction of authority URI from subject (650)."""
        record = Record()
        record.add_field(
            Field(
                tag='650',
                indicators=[' ', '0'],
                subfields=[
                    Subfield(code='a', value='Printing'),
                    Subfield(code='z', value='Italy'),
                    Subfield(code='v', value='Bibliography'),
                    Subfield(code='0', value='http://id.loc.gov/authorities/subjects/sh85106837'),
                ]
            )
        )

        subjects = extract_subjects(record)

        assert len(subjects) == 1
        subj = subjects[0]
        assert 'Printing' in subj.value
        assert subj.authority_uri is not None
        assert subj.authority_uri.value == 'http://id.loc.gov/authorities/subjects/sh85106837'
        assert '650[0]$0' in subj.authority_uri.source

    def test_subject_with_nli_authority_uri(self):
        """Test extraction of NLI authority URI from subject."""
        record = Record()
        record.add_field(
            Field(
                tag='650',
                indicators=[' ', '4'],
                subfields=[
                    Subfield(code='a', value='ספרים נדירים'),
                    Subfield(code='2', value='nli'),
                    Subfield(code='0', value='https://open-eu.hosted.exlibrisgroup.com/alma/972NNL_INST/authorities/987007261327805171.jsonld'),
                ]
            )
        )

        subjects = extract_subjects(record)

        assert len(subjects) == 1
        subj = subjects[0]
        assert subj.authority_uri is not None
        assert 'exlibrisgroup.com' in subj.authority_uri.value
        assert subj.scheme.value == 'nli'

    def test_geographic_subject_with_authority_uri(self):
        """Test extraction of authority URI from geographic subject (651)."""
        record = Record()
        record.add_field(
            Field(
                tag='651',
                indicators=[' ', '0'],
                subfields=[
                    Subfield(code='a', value='Venice (Italy)'),
                    Subfield(code='x', value='History'),
                    Subfield(code='0', value='http://id.loc.gov/authorities/names/n79022936'),
                ]
            )
        )

        subjects = extract_subjects(record)

        assert len(subjects) == 1
        subj = subjects[0]
        assert 'Venice (Italy)' in subj.value
        assert subj.authority_uri is not None
        assert subj.authority_uri.value == 'http://id.loc.gov/authorities/names/n79022936'
        assert '651[0]$0' in subj.authority_uri.source

    def test_subject_without_authority_uri(self):
        """Test that subjects without $0 have authority_uri=None."""
        record = Record()
        record.add_field(
            Field(
                tag='650',
                indicators=[' ', '0'],
                subfields=[
                    Subfield(code='a', value='Incunabula'),
                ]
            )
        )

        subjects = extract_subjects(record)

        assert len(subjects) == 1
        assert subjects[0].authority_uri is None
