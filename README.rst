=================================
Async Lutron Integration Protocol
=================================


.. image:: https://img.shields.io/pypi/v/aiolip.svg
        :target: https://pypi.python.org/pypi/aiolip

.. image:: https://img.shields.io/travis/bdraco/aiolip.svg
        :target: https://travis-ci.com/bdraco/aiolip

.. image:: https://readthedocs.org/projects/aiolip/badge/?version=latest
        :target: https://aiolip.readthedocs.io/en/latest/?badge=latest
        :alt: Documentation Status




Async Lutron Integration Protocol


* Free software: Apache Software License 2.0
* Documentation: https://aiolip.readthedocs.io.


Example Usage
-------------

.. code-block:: python

        import asyncio
        import logging

        from aiolip import LIP
        from aiolip.data import LIPMode

        _LOGGER = logging.getLogger(__name__)


        async def main():
        lip = LIP()

        logging.basicConfig(level=logging.DEBUG)

        await lip.async_connect("192.168.209.70")

        def message(msg):
                _LOGGER.warning(msg)

        lip.subscribe(message)
        run_task = asyncio.create_task(lip.async_run())
        await run_task
        await lip.async_stop()

        if __name__ == "__main__":
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())

Credits
-------

This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_ project template.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage
