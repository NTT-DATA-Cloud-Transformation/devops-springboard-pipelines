#!/usr/bin/env python
import boto3
import argparse
import os
import logging
import yaml


def upload_to_s3(s3_client, template_path, bucket_name, bucket_prefix,):
    """

    :param s3_client:
    :param template_path:
    :param bucket_prefix:
    :param bucket_name:
    :return:
    """
    file_parts = template_path.split(".")
    file_name_without_ext = file_parts[0]
    upload_path = file_name_without_ext + "_" \
        + get_codebuild_version() + file_parts[1]
    key_name = bucket_prefix + upload_path
    s3_client.put_object(
        Body=open(template_path),
        Bucket=bucket_name,
        Key=key_name
    )
    s3_url = "{}/{}/{}".format(s3_client.meta.endpoint_url, bucket_name, key_name)
    return s3_url


def parse_arguments():
    """
    To parse the command line arguments passed to script
    :return:
    """
    parser = argparse.ArgumentParser(description='Product Creation/Updation')
    parser.add_argument('--log_level', '-ll', default='WARN', type=str.upper,
                        choices=['DEBUG', 'INFO', 'WARN', 'ERROR'], help='Set log level')
    parser.add_argument('--bucket_name', '-bn',
                        help='Bucket name for storing templates for products of service catalog', required=True)
    parser.add_argument('--bucket_path', '-bp',
                        help='S3 bucket folder path for storing templates for products of service catalog',
                        required=True)
    parser.add_argument('--conf', '-c',
                        help='The configuration file for products', required=True, default='service-catalog-conf.yml')
    args = parser.parse_args()
    return args


def configure_logging(log_level):
    """
    to set the logging level
    :param log_level:
    :return:
    """
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % log_level)

    logging.basicConfig(level=numeric_level)


def get_codebuild_version():
    return os.environ['CODEBUILD_RESOLVED_SOURCE_VERSION'][:8].replace(".", "")


def create_product(client, product_conf, s3_url):
    """
    Create new Product
    :param client:
    :param product_conf:
    :param s3_url:
    :return:
    """
    logging.info("creating product {0}".format(product_conf['Name']))
    if 'Version' in product_conf:
        version = product_conf['Version']['Name']
        description = product_conf['Version'].get('Description')
    else:
        version = get_codebuild_version()
        description = "initial version"
    response = client.create_product(
        Name=product_conf['Name'],
        Owner=product_conf['Owner'],
        Description=product_conf['Description'],
        Distributor=product_conf['Owner'],
        SupportDescription=product_conf['Description'],
        SupportEmail=product_conf['SupportEmail'],
        SupportUrl=product_conf['SupportUrl'],
        ProductType='CLOUD_FORMATION_TEMPLATE',
        ProvisioningArtifactParameters={
         'Name': version,
         'Description': description,
         'Info': {'LoadTemplateFromURL': s3_url},
         'Type': 'CLOUD_FORMATION_TEMPLATE'
        }
    )
    if response['ProductViewDetail']['Status'] == 'CREATED':
        logging.info("product creation successful ")
    product_dict = {
        "product_id": response['ProductViewDetail']['ProductViewSummary']['ProductId'],
        "product_version_id": response['ProvisioningArtifactDetail']['Name'],
        "product_version_name": response['ProvisioningArtifactDetail']['Name']
    }
    return product_dict


def create_version_of_product(conn, version, s3_url, product_id, product_name, description=""):
    """
    create a new version for an existing product
    :param conn:
    :param version:
    :param s3_url:
    :param product_id:
    :param product_name:
    :param description:
    :return:
    """
    client = conn['service_catalog_client']
    client.create_provisioning_artifact(
        ProductId=product_id,
        Parameters={
           'Name': version,
           'Description': description,
           'Info': {
               'LoadTemplateFromURL': s3_url
           },
           'Type': 'CLOUD_FORMATION_TEMPLATE'
        },
        )

    logging.info("new version  {} created for product {} in region {}".format(
        version, product_name, conn['region']))


def create_portfolio(client, portfolio_conf, region):
    """
    To create the portfolio
    :param client:
    :param portfolio_conf:
    :param region:
    :return:
    """
    response = client.create_portfolio(
        DisplayName=portfolio_conf['Name'],
        Description=portfolio_conf['Description'],
        ProviderName=portfolio_conf['Provider']

    )
    portfolio_id = response['PortfolioDetail']['Id']
    logging.info("portfolio {} created in region {}".format(portfolio_conf['Name'], region))
    return portfolio_id


def attach_product_to_portfolio(client, product_id, portfolio_id):
    """
    To attach the product to portfolio
    :rtype: object
    :param client:
    :param product_id:
    :param portfolio_id:
    :return:
    """
    client.associate_product_with_portfolio(
        ProductId=product_id,
        PortfolioId=portfolio_id,
    )


def compare_templates(conn, template_url, product_name, product_template):
    """
    To compare the new and old template for same product and inform if there is any change in template.
    :param conn:
    :param template_url:
    :param product_name:
    :param product_template:
    :return:
    """
    s3_client = conn[2]
    object_info_list = template_url.split("/", 4)
    bucket = object_info_list[3]
    key = object_info_list[4].split(".yml")[0]+".yml"
    logging.debug("bucket: {}".format(bucket))
    logging.debug("key: {}".format(key))
    with open('temp_template.yml', 'wb') as data:
        s3_client.download_fileobj(bucket, key, data)

    old_template_path = 'temp_template.yml'
    new_template_path = 'cf-templates/{}/{}'.format(product_name, product_template)
    diff_set = set()
    with open(new_template_path) as f1, open(old_template_path) as f2:
        difference = set(f1).difference(f2)

    logging.debug("difference: {}".format(difference))
    if difference == diff_set:
        logging.debug("status: {}".format(False))
        logging.debug("old_template_path: {}".format(old_template_path))
        return False, old_template_path
    else:
        logging.debug("status: {}".format(True))
        logging.debug("new_template_path: {}".format(new_template_path))
        return True, new_template_path


def get_latest_version_template_from_product(service_catalog_client, latest_version_id, product_id):
    """
    Get the latest template from product
    :param service_catalog_client:
    :param latest_version_id:
    :param product_id:
    :return:
    """
    response = service_catalog_client.describe_provisioning_artifact(
        ProvisioningArtifactId=latest_version_id, ProductId=product_id)
    logging.debug("latest template: {}".format(response['Info']['TemplateUrl']))
    return response['Info']['TemplateUrl']


def get_portfolio(portfolio_conf):
    """
    search portfolio if it not present then create it.
    :param portfolio_conf:
    :return:
    """
    conn = create_connections()
    paginator = conn['service_catalog_client'].get_paginator('list_portfolios')
    page_iterator = paginator.paginate()
    portfolio_id = None
    for page in page_iterator:
        for portfolio in page['PortfolioDetails']:
            if portfolio['DisplayName'] == portfolio_conf['Name']:
                logging.info("portfolio {} already exist in region {}".format(portfolio_conf['Name'], conn['region']))
                portfolio_id = portfolio['Id']
                break

        if portfolio_id is not None:
            break
    else:
        portfolio_id = create_portfolio(conn['service_catalog_client'], portfolio_conf, conn['region'])
    return portfolio_id


def get_conf(conf_file):
    """
    Read and parse the configuration file and return a corresponding dictionary
    :param conf_file:
    :return:
    """
    with open(conf_file, 'r') as f:
        config = yaml.load(f.read())
    return config


def create_connections():
    """
    A utility function to create boto3 clients
    :return:
    """
    conn = {}
    region = os.environ['AWS_DEFAULT_REGION']
    conn['service_catalog_client'] = boto3.client('servicecatalog', region_name=region)
    conn['s3_client'] = boto3.client('s3', region_name=region)
    conn['region'] = region
    return conn


def create_update_product(product_conf, portfolio_id, bucket_name, bucket_path):
    """
    Create or Update service catalog product and associate it with the given portfolio
    :param product_conf:
    :param portfolio_id:
    :param bucket_name:
    :param bucket_path:
    :return:
    """
    conn = create_connections()
    product_name = product_conf['Name']
    product_template = product_conf['TemplatePath']
    product_temp_s3_url = '{}/{}/{}'.format(conn['s3_client'].meta.endpoint_url, bucket_name,
                                            "{}/cf-templates/{}/{}".format(bucket_path, product_name,
                                                                           product_template))
    logging.info(product_temp_s3_url)
    logging.info("product_name={}".format(product_name))
    logging.debug("product template name: {}/{}\n".format(product_name, product_template))

    # Check if the product exists, If not create it.
    response = conn['service_catalog_client'].search_products_as_admin(Filters={'FullTextSearch': [product_name]})
    for product in response['ProductViewDetails']:
        logging.debug("found: {0} ".format(product['ProductViewSummary']['Name']))
        if product['ProductViewSummary']['Name'] == product_name:
            product_id = product['ProductViewSummary']['ProductId']
            logging.debug("product_id: {}".format(product_id))
            version_response = conn['service_catalog_client'].describe_product_as_admin(Id=product_id)
            versions = version_response['ProvisioningArtifactSummaries']
            product_latest_version = max(
                versions,
                key=lambda x: x['CreatedTime'].timetuple()
            )
            logging.info("product_latest_version_id: {}".format(product_latest_version['Id']))
            logging.info("product_latest_version_name: {}".format(product_latest_version['Name']))
            if product_conf.get('Version'):
                version = product_conf.get('Version').get('Name')
                description = product_conf.get('Version').get('Description', '')
                if version == product_latest_version['Name']:
                    # Do not update the template
                    logging.info("product {0} has not been updated".format(product_conf['Name']))
                else:
                    # Update the product
                    s3_url = upload_to_s3(
                        conn['s3_client'],
                        product_conf['TemplatePath'], bucket_name, bucket_path
                    )
                    create_version_of_product(
                        conn, version, s3_url, product_id, product_name, description=description)

            else:
                # Get latest template for that product
                template_latest = get_latest_version_template_from_product(
                    conn['service_catalog_client'], product_latest_version['Id'], product_id)
                comp_status = compare_templates(
                    conn, template_latest, product_name, product_template)
                if comp_status[0]:
                    version = get_codebuild_version()
                    logging.info(version)
                    # upload new template to bucket for new version
                    s3_url = upload_to_s3(
                        conn['s3_client'],
                        product_conf['TemplatePath'], bucket_name, bucket_path
                    )
                    create_version_of_product(
                        conn, version, s3_url, product_id, product_name)

            break
    else:
        # upload template for product creation
        s3_url = upload_to_s3(
            conn['s3_client'],
            product_conf['TemplatePath'], bucket_name, bucket_path
        )
        product_dict = create_product(conn['service_catalog_client'], product_conf, s3_url)
        # associate the product with portfolio
        attach_product_to_portfolio(conn['service_catalog_client'], product_dict['product_id'], portfolio_id)


def main(args):
    """
    The main method to handle products and portfolios
    :param args:
    :return:
    """
    configure_logging(args.log_level)
    bucket_name = args.bucket_name
    bucket_path = args.bucket_path
    config = get_conf(args.conf)
    for portfolio in config.get('Portfolios', []):
        portfolio_id = get_portfolio(portfolio)
        products = portfolio.get('Products', [])
        for product_conf in products:
            # To create/update product one by one.
            create_update_product(product_conf, portfolio_id, bucket_name, bucket_path)

            
if __name__ == "__main__":
    # To get the parsed arguments
    ARGS = parse_arguments()
    main(ARGS)
